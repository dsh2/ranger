# -*- encoding: utf8 -*-
# Copyright (C) 2009, 2010, 2011  Roman Zimbelmann <romanz@lavabit.com>
# This software is distributed under the terms of the GNU GPL version 3.

"""The BrowserColumn widget displays the contents of a directory or file."""
import stat
import curses
from time import time

from . import Widget
from .pager import Pager
from ranger.fsobject import BAD_INFO
from ranger.ext.widestring import WideString

class BrowserColumn(Pager):
	main_column = False
	display_infostring = False
	scroll_begin = 0
	target = None
	last_redraw_time = -1
	ellipsis = { False: '~', True: '…' }

	old_dir = None
	old_cf = None

	def __init__(self, win, level):
		"""
		win = the curses window object of the BrowserView
		level = what to display?

		level >0 => previews
		level 0 => current file/directory
		level <0 => parent directories
		"""
		Pager.__init__(self, win)
		Widget.__init__(self, win)
		self.level = level

		self.settings.signal_bind('setopt.display_size_in_main_column',
				self.request_redraw, weak=True)

	def request_redraw(self):
		self.need_redraw = True

	def resize(self, y, x, hei, wid):
		Widget.resize(self, y, x, hei, wid)

	def click(self, event):
		"""Handle a MouseEvent"""
		direction = event.mouse_wheel_direction()
		if not (event.pressed(1) or event.pressed(3) or direction):
			return False

		if self.target is None:
			pass

		elif self.target.is_directory:
			if self.target.accessible and self.target.content_loaded:
				index = self.scroll_begin + event.y - self.y

				if direction:
					if self.level == -1:
						self.fm.move_parent(direction)
					else:
						return False
				elif event.pressed(1):
					if not self.main_column:
						self.fm.enter_dir(self.target.path)

					if index < len(self.target):
						self.fm.move(to=index)
				elif event.pressed(3):
					try:
						clicked_file = self.target.files[index]
						if clicked_file.is_directory:
							self.fm.enter_dir(clicked_file.path)
						elif self.level == 0:
							self.fm.env.cwd.move_to_obj(clicked_file)
							self.fm.execute_file(clicked_file)
					except:
						pass

		else:
			if self.level > 0 and not direction:
				self.fm.move(right=0)

		return True

	def execute_curses_batch(self, line, data):
		self.win.move(line, 0)
		for entry in data:
			text, attr = entry
			self.win.attrset(attr)
			try:
				self.win.addstr(text)
			except:
				pass

	def has_preview(self):
		if self.target is None:
			return False

		if self.target.is_file:
			if not self.target.has_preview():
				return False

		if self.target.is_directory:
			if self.level > 0 and not self.settings.preview_directories:
				return False

		return True

	def poke(self):
		Widget.poke(self)
		self.target = self.env.at_level(self.level)

	def draw(self):
		"""Call either _draw_file() or _draw_directory()"""
		if self.target != self.old_dir:
			self.need_redraw = True
			self.old_dir = self.target

		if self.target:  # don't garbage collect this directory please
			self.target.use()

		if self.target and self.target.is_directory \
				and (self.level <= 0 or self.settings.preview_directories):
			if self.target.pointed_obj != self.old_cf:
				self.need_redraw = True
				self.old_cf = self.target.pointed_obj

			if self.target.load_content_if_outdated() \
			or self.target.sort_if_outdated() \
			or self.last_redraw_time < self.target.last_update_time:
				self.need_redraw = True

		if self.need_redraw:
			self.win.erase()
			if self.target is None:
				pass
			elif self.target.is_file:
				Pager.open(self)
				self._draw_file()
			elif self.target.is_directory:
				self._draw_directory()
				Widget.draw(self)
			self.need_redraw = False
			self.last_redraw_time = time()

	def _draw_file(self):
		"""Draw a preview of the file, if the settings allow it"""
		self.win.move(0, 0)
		if not self.target.accessible:
			self.addnstr("not accessible", self.wid)
			Pager.close(self)
			return

		if self.target is None or not self.target.has_preview():
			Pager.close(self)
			return

		f = self.target.get_preview_source(self.wid, self.hei)
		if f is None:
			Pager.close(self)
		else:
			self.set_source(f)
			Pager.draw(self)

	def _draw_directory(self):
		"""Draw the contents of a directory"""

		if self.level > 0 and not self.settings.preview_directories:
			return

		base_color = ['in_browser']

		self.win.move(0, 0)

		if not self.target.content_loaded:
			self.color(tuple(base_color))
			self.addnstr("...", self.wid)
			self.color_reset()
			return

		if self.main_column:
			base_color.append('main_column')

		if not self.target.accessible:
			self.color(tuple(base_color + ['error']))
			self.addnstr("not accessible", self.wid)
			self.color_reset()
			return

		if self.target.empty():
			self.color(tuple(base_color + ['empty']))
			self.addnstr("empty", self.wid)
			self.color_reset()
			return

		self._set_scroll_begin()

		copied = [f.path for f in self.env.copy]
		ellipsis = self.ellipsis[self.settings.unicode_ellipsis]

		selected_i = self.target.pointer
		for line in range(self.hei):
			i = line + self.scroll_begin
			if line > self.hei:
				break

			try:
				drawn = self.target.files[i]
			except IndexError:
				break

			tagged = self.fm.tags and drawn.realpath in self.fm.tags
			if tagged:
				tagged_marker = self.fm.tags.marker(drawn.realpath)
			else:
				tagged_marker = " "

			key = (self.wid, selected_i == i, drawn.marked, drawn.path in copied, tagged_marker)

			if key in drawn.display_data:
				self.execute_curses_batch(line, drawn.display_data[key])
				continue

			display_data = []
			drawn.display_data[key] = display_data

			if self.display_infostring and drawn.infostring \
					and self.settings.display_size_in_main_column:
				infostring = str(drawn.infostring) + " "
			else:
				infostring = ""

			this_color = base_color + list(drawn.mimetype_tuple)
			text = drawn.basename

			space = self.wid - len(infostring)
			if self.main_column:
				space -= 2
			elif self.settings.display_tags_in_all_columns:
				space -= 1

			if i == selected_i:
				this_color.append('selected')

			if drawn.marked:
				this_color.append('marked')
				if self.main_column or self.settings.display_tags_in_all_columns:
					text = " " + text

			if tagged:
				this_color.append('tagged')

			if drawn.is_directory:
				this_color.append('directory')
			else:
				this_color.append('file')

			if drawn.stat:
				mode = drawn.stat.st_mode
				if mode & stat.S_IXUSR:
					this_color.append('executable')
				if stat.S_ISFIFO(mode):
					this_color.append('fifo')
				if stat.S_ISSOCK(mode):
					this_color.append('socket')
				if drawn.is_device:
					this_color.append('device')

			if drawn.path in copied:
				this_color.append('cut' if self.env.cut else 'copied')

			if drawn.is_link:
				this_color.append('link')
				this_color.append(drawn.exists and 'good' or 'bad')

			attr = self.settings.colorscheme.get_attr(*this_color)

			if (self.main_column or self.settings.display_tags_in_all_columns) \
					and tagged and self.wid > 2:
				this_color.append('tag_marker')
				tag_attr = self.settings.colorscheme.get_attr(*this_color)
				display_data.append([tagged_marker, tag_attr])
			else:
				text = " " + text

			wtext = WideString(text)
			if len(wtext) > space:
				wtext = wtext[:space - 1] + ellipsis
			text = str(wtext)

			display_data.append([text, attr])

			if infostring:
				if len(text) + 1 + len(infostring) > self.wid:
					pass
				else:
					padding = self.wid - len(wtext) - len(infostring)
					if tagged and (self.main_column or \
							self.settings.display_tags_in_all_columns):
						padding -= 1
					infostring = (" " * padding) + infostring
					display_data.append([infostring, attr])

			self.execute_curses_batch(line, display_data)

	def _get_scroll_begin(self):
		"""Determines scroll_begin (the position of the first displayed file)"""
		offset = self.settings.scroll_offset
		dirsize = len(self.target)
		winsize = self.hei
		halfwinsize = winsize // 2
		index = self.target.pointer or 0
		original = self.target.scroll_begin
		projected = index - original

		upper_limit = winsize - 1 - offset
		lower_limit = offset

		if original < 0:
			return 0

		if dirsize < winsize:
			return 0

		if halfwinsize < offset:
			return min( dirsize - winsize, max( 0, index - halfwinsize ))

		if original > dirsize - winsize:
			self.target.scroll_begin = dirsize - winsize
			return self._get_scroll_begin()

		if projected < upper_limit and projected > lower_limit:
			return original

		if projected > upper_limit:
			return min( dirsize - winsize,
					original + (projected - upper_limit))

		if projected < upper_limit:
			return max( 0,
					original - (lower_limit - projected))

		return original

	def _set_scroll_begin(self):
		"""Updates the scroll_begin value"""
		self.scroll_begin = self._get_scroll_begin()
		self.target.scroll_begin = self.scroll_begin

	def scroll(self, n):
		"""scroll down by n lines"""
		self.need_redraw = True
		self.target.move(down=n)
		self.target.scroll_begin += 3 * n

	def __str__(self):
		return self.__class__.__name__ + ' at level ' + str(self.level)
