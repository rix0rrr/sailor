import calendar
import curses
import curses.ascii
from curses import textpad
import datetime
import itertools
import logging
import os
import string

logger = logging.getLogger('sailor')

CTRL_A = 1
CTRL_E = ord('e') - ord('a') + 1
CTRL_J = ord('j') - ord('a') + 1
CTRL_K = ord('k') - ord('a') + 1
CTRL_N = ord('n') - ord('a') + 1
CTRL_P = ord('p') - ord('a') + 1

MAC_BACKSPACE = 127   # Don't feel like finding out why
SHIFT_TAB = 353
CR = 13  # Or Ctrl-M, so don't use that

black = curses.COLOR_BLACK
red = curses.COLOR_RED
green = curses.COLOR_GREEN
white = curses.COLOR_WHITE
blue = curses.COLOR_BLUE
cyan = curses.COLOR_CYAN
magenta = curses.COLOR_MAGENTA
yellow = curses.COLOR_YELLOW

# FIXME: Crash when running off the edges

def reduce_esc_delay():
  try:
    os.environ['ESCDELAY']
  except KeyError:
    os.environ['ESCDELAY'] = '25'


def is_enter(ev):
  return ev.key in [curses.KEY_ENTER, CR]


def ident(x):
  return x


def get_value(x):
  return x.value if isinstance(x, Option) else x


def flatten(listOfLists):
    return itertools.chain.from_iterable(listOfLists)


class Colorized(object):
  def __init__(self, text, color, attr=0):
    self.text = text
    self.color = color
    self.attr = attr

  def __str__(self):
    return '\0' + str(self.color) + '\1' + str(self.attr) + '\1' + str(self.text) + '\0'


#----------------------------------------------------------------------
#  VIEW classes

class View(object):
  def size(self, rect):
    return (0, 0)

  def display(self, rect):
    self.rect = rect
    if rect.w > 0 and rect.h > 0:
      self.disp(rect)

  def disp(self, rect):
    raise RuntimeError('Not implemented: disp()')


class Display(View):
  def __init__(self, text, min_width=0, fg=white, bg=black, attr=0):
    self.lines = str(text).split('\n')
    self.fg = fg
    self.bg = bg
    self.min_width = min_width
    self.attr = attr

  @property
  def text(self):
    return '\n'.join(self.lines)

  def size(self, rect):
    return max(self.min_width, max(len(l) for l in self.lines)), len(self.lines)

  def disp(self, rect):
    col = rect.get_color(self.fg, self.bg)
    print_width = max(0, rect.w)
    lines = self.lines[:rect.h]
    if print_width > 0 and lines:
      for i, line in enumerate(lines):
        padding = ' ' * min(print_width, self.min_width - len(line))
        try:
          rect.screen.addstr(rect.y + i, rect.x, line[:print_width] + padding, curses.color_pair(col) | self.attr)
        except curses.error, e:
          logger.warn(str(e))


class Positioned(View):
  def __init__(self, inner, x=-1, y=-1):
    self.inner = inner
    self.x = x
    self.y = y

  def size(self, rect):
    return self.inner.size(rect)

  def disp(self, rect):
    size = self.size(rect)

    x = max(0, min(self.x, rect.w - size[0]))
    irect = Rect(rect.app, rect.screen, x, self.y, size[0], size[1])
    irect.clear()
    self.inner.display(irect)


class Centered(View):
  def __init__(self, inner):
    self.inner = inner

  def size(self, rect):
    return rect

  def disp(self, rect):
    size = self.inner.size(rect)
    x = (rect.w - size[0]) / 2
    y = (rect.h - size[1]) / 2
    irect = rect.sub_rect(x, y, size[0], size[1])
    self.inner.display(irect)


class AlignRight(View):
  def __init__(self, inner, h_margin=2, v_margin=1):
    self.inner = inner
    self.h_margin = h_margin
    self.v_margin = v_margin

  def size(self, rect):
    return rect.w, rect.h

  def disp(self, rect):
    w, h = self.inner.size(rect)
    irect = rect.adj_rect(rect.w - w - self.h_margin, self.v_margin)
    self.inner.display(irect)


class HFill(View):
  def __init__(self, char, fg=white, bg=black):
    self.char = char
    self.fg = fg
    self.bg = bg

  def size(self, rect):
    return rect.w, 1

  def disp(self, rect):
    col = rect.get_color(self.fg, self.bg)
    rect.screen.addstr(rect.y, rect.x, self.char * rect.w, curses.color_pair(col))


class Horizontal(View):
  def __init__(self, views, margin=0):
    assert(all(views))
    self.views = views
    self.margin = margin

  def size(self, rect):
    sizes = []
    for v in self.views:
      sizes.append(v.size(rect))
      rect = rect.adj_rect(sizes[-1][0], 0)

    widths = [s[0] for s in sizes]
    heights = [s[1] for s in sizes]
    return sum(widths) + max(len(self.views) - 1, 0) * self.margin, max(heights + [0])

  def disp(self, rect):
    for v in self.views:
      v.display(rect)
      dx = v.size(rect)[0] + self.margin
      rect = rect.adj_rect(dx, 0)


class Grid(View):
  def __init__(self, grid, h_margin=1, align_right=False):
    self.grid = grid
    self.h_margin = h_margin
    self.align_right = align_right

  def size(self, rect):
    # FIXME: Not correct for size-adapting controls
    self.size_grid = [[col.size(rect) for col in row]
                      for row in self.grid]
    cols = len(self.size_grid[0])
    self.col_widths = [max(self.size_grid[i][col_nr][0] for i in range(len(self.size_grid)))
                       for col_nr in range(cols)]
    self.row_heights = [max(col[1] for col in row)
                        for row in self.size_grid]
    w = sum(self.col_widths) + (len(self.col_widths) - 1) * self.h_margin
    h = sum(self.row_heights)
    return w, h

  def disp(self, rect):
    for j, row in enumerate(self.grid):
      rrect = rect.adj_rect(0, sum(self.row_heights[:j]))
      for i, cell in enumerate(row):
        col_width = self.col_widths[i]
        cell_size = cell.size(rect)
        if self.align_right:
          rrect = rrect.adj_rect(col_width - cell_size[0], 0)
        cell.display(rrect)
        rrect = rrect.adj_rect(cell_size[0] + self.h_margin, 0)


class Vertical(View):
  def __init__(self, views, margin=0):
    self.views = views
    self.margin = margin

  def size(self, rect):
    sizes = []
    for v in self.views:
      sizes.append(v.size(rect))
      rect = rect.adj_rect(0, sizes[-1][1])

    widths = [s[0] for s in sizes]
    heights = [s[1] for s in sizes]
    return max(widths + [0]), sum(heights) + max(len(self.views) - 1, 0) * self.margin

  def disp(self, rect):
    for v in self.views:
      v.display(rect)
      dy = v.size(rect)[1] + self.margin
      rect = rect.adj_rect(0, dy)


class Box(View):
  def __init__(self, inner, caption=None, underscript=None, x_margin=1, y_margin=0, x_fill=True, y_fill=False):
    self.inner = inner
    self.caption = caption
    self.underscript = underscript
    self.x_margin = x_margin
    self.y_margin = y_margin
    self.x_fill = x_fill
    self.y_fill = y_fill

  def size(self, rect):
    if not self.x_fill or not self.y_fill:
      inner_size = self.inner.size(rect.adj_rect(1 + self.x_margin, 1 + self.y_margin, 1 + self.x_margin, 1 + self.y_margin))
    w = rect.w if self.x_fill else inner_size[0] + 2 * (1 + self.x_margin)
    h = rect.h if self.y_fill else inner_size[1] + 2 * (1 + self.y_margin)
    return w, h

  def disp(self, rect):
    size = self.size(rect)

    rect_w = min(size[0], rect.w)
    rect_h = min(size[1], rect.h)

    if rect_w > 0 and rect_h > 0:
      x1 = rect.x + rect_w - 1
      y1 = rect.y + rect_h - 1

      # Make sure that we don't draw to the complete end of the screen, because that'll break
      screen_h = rect.screen.getmaxyx()[0]
      y1 = min(y1, screen_h - 2)

      try:
        rect.resize(rect_w, rect_h).clear()
        textpad.rectangle(rect.screen, rect.y, rect.x, y1, x1)
        if self.caption:
          self.caption.display(rect.adj_rect(3, 0))
        if self.underscript:
          s = self.underscript.size(rect)
          self.underscript.display(rect.adj_rect(max(3, rect_w - s[0] - 3), rect_h - 1))
      except curses.error, e:
        # We should not have sent this invalid draw command...
        logger.warn(e)
      try:
        self.inner.display(rect.adj_rect(1 + self.x_margin, 1 + self.y_margin, 1 + self.x_margin, 1 + self.y_margin))
      except curses.error, e:
        # We should not have sent this invalid draw command...
        logger.warn(e)


#----------------------------------------------------------------------
#  CONTROL classes


class Control(object):
  def __init__(self, fg=white, bg=black, id=None):
    self.fg = fg
    self.bg = bg
    self.id = id
    self.can_focus = False
    self.controls = []

  def render(self, app):
    raise RuntimeError('Not implemented: render()')

  def children(self):
    return self.controls

  def on_event(self, ev):
    pass

  def contains(self, ctrl):
    if ctrl is self:
      return True

    for child in self.controls:
      if child.contains(ctrl):
        return True

    return False

  def find(self, id):
    for parent, child in object_tree(self):
      if child.id == id:
        return child
    raise RuntimeError('No such control: %s' % id)

  def _focus_order(self, key):
    return (reversed
            if key in [curses.KEY_UP, curses.KEY_LEFT, SHIFT_TAB] else
            ident)

  def enter_focus(self, key, app):
    if self.can_focus:
      app.layer(self).focus(self)
      return True

    order = self._focus_order(key)

    for child in order(self.children()):
      if child.enter_focus(key, app):
        return True
    return False


class Text(Control):
  def __init__(self, value, **kwargs):
    super(Text, self).__init__(**kwargs)
    self.value = value
    self.can_focus = False

  @property
  def text(self):
    return self.value

  def render(self, app):
    return Display(self.value, fg=self.fg, bg=self.bg)


def propagate_focus(ev, controls, layer, keys_back, keys_fwd):
  """Propagate focus events forwards and backwards through a list of controls."""
  if ev.type == 'key':
    if ev.key in keys_back + keys_fwd:
      back = ev.key in keys_back
      current = ev.app.find_ancestor(ev.last, controls)
      if not current:
        return False

      i = controls.index(current)
      while 0 <= i < len(controls) and ev.propagating:
        i += -1 if back else 1
        if 0 <= i < len(controls) and controls[i].enter_focus(ev.key, ev.app):
          ev.stop()
          return True
  return False


class Panel(Control):
  def __init__(self, controls, caption=None, underscript=None, **kwargs):
    super(Panel, self).__init__(**kwargs)
    self.controls = controls
    self.caption = caption
    self.underscript = None

  def render(self, app):
    return Box(Vertical([c.render(app) for c in self.controls]),
               caption=self.caption.render(app) if self.caption else None,
               underscript=self.underscript.render(app) if self.underscript else None)

  def on_event(self, ev):
    propagate_focus(ev, self.controls, ev.app.layer(self),
                    [curses.KEY_UP, SHIFT_TAB],
                    [curses.KEY_DOWN, curses.ascii.TAB])


class Stacked(Control):
  def __init__(self, controls, **kwargs):
    super(Stacked, self).__init__(**kwargs)
    self.controls = controls

  def render(self, app):
    return Vertical([c.render(app) for c in self.controls])

  def on_event(self, ev):
    propagate_focus(ev, self.controls, ev.app.layer(self),
                    [curses.KEY_UP, SHIFT_TAB],
                    [curses.KEY_DOWN, curses.ascii.TAB])


class Option(object):
  """Helper class to attach data to a string."""
  def __init__(self, value, caption=None):
    self.value = value
    self.caption = caption or str(value)

  def __str__(self):
    return self.caption

  def __eq__(self, other):
    if not isinstance(other, Option):
      return self.value == other
    return self.value == other.value

  def __ne__(self, other):
    return not self.__eq__(other)

  def __hash__(self):
    return hash(self.value)

  def __str__(self):
    return self.caption

  def __repr__(self):
    return 'Option(%r, %r)' % (self.value, self.caption)


class Labeled(Control):
  def __init__(self, label, control, **kwargs):
    super(Labeled, self).__init__(**kwargs)
    assert(control)
    self.label   = label
    self.control = control

  def render(self, app):
    fg = white if app.contains_focus(self) else green
    attr = curses.A_BOLD if app.contains_focus(self) else 0
    return Horizontal([Display(self.label, min_width=16, fg=fg, attr=attr),
                       self.control.render(app)])

  def children(self):
    return [self.control]


class SelectList(Control):
  def __init__(self, choices, index, width=30, height=10, show_captions_at=0, **kwargs):
    super(SelectList, self).__init__(**kwargs)
    self.choices = choices
    self.index = index
    self.width = width
    self.height = height
    self.scroll_offset = max(0, min(self.index, len(self.choices) - height))
    self.can_focus = True
    self.show_captions_at = show_captions_at

  def adjust(self, d):
    if len(self.choices) > 1:
      self.index = (self.index + d + len(self.choices)) % len(self.choices)
      self.scroll_offset = min(self.scroll_offset, self.index)
      self.scroll_offset = max(self.scroll_offset, self.index - self.height + 1)

  def sanitize_index(self):
    self.index = min(max(0, self.index), len(self.choices) - 1)
    return 0 <= self.index < len(self.choices)

  @property
  def value(self):
    return get_value(self.choices[self.index])

  @value.setter
  def value(self, value):
    self.index = max(0, self.choices.index(value))

  def _render_line(self, line, selected):
    attr = curses.A_STANDOUT if selected else 0
    if self.show_captions_at and isinstance(line, Option):
      rem = self.width - self.show_captions_at
      return Horizontal([
          Display(str(line.value)[:self.show_captions_at], min_width=self.show_captions_at, attr=attr),
          Display(str(line.caption)[:rem], min_width=rem, attr=attr, fg=cyan if not selected else white)
          ])
    return Display(line, min_width=self.width, attr=attr)

  def render(self, app):
    self.sanitize_index()

    lines = self.choices[self.scroll_offset:self.scroll_offset + self.height]
    lines.extend([''] * (self.height - len(lines)))

    vert = Vertical([self._render_line(l, i + self.scroll_offset == self.index) for i, l in enumerate(lines)])

    # FIXME: Scroll bar
    return vert

  def on_event(self, ev):
    if ev.type == 'key':
      if ev.key == curses.KEY_UP and 0 < self.index:
        self.index -= 1
        self.scroll_offset = min(self.scroll_offset, self.index)
        ev.stop()
      if ev.key == curses.KEY_DOWN and self.index < len(self.choices) - 1:
        self.index += 1
        self.scroll_offset = max(self.scroll_offset, self.index - self.height + 1)
        ev.stop()
      if ev.key == curses.KEY_HOME:
        self.index = 0
        ev.stop()
      if ev.key == curses.KEY_END:
        self.index = len(self.choices) - 1
        ev.stop()


class SelectDate(Control):
  def __init__(self, value=None, **kwargs):
    super(Control, self).__init__(**kwargs)
    self.can_focus = True
    self.value = value or datetime.datetime.now()

  def _render_monthcell(self, cell):
    if not cell:
      return Display('')
    attr = 0
    if cell == self.value.day:
      attr = curses.A_STANDOUT if self.has_focus else curses.A_UNDERLINE
    return Display(str(cell), attr=attr)

  @property
  def date(self):
    return self.value.date()

  def render(self, app):
    self.has_focus = app.contains_focus(self)
    cal_data = calendar.monthcalendar(self.value.year, self.value.month)
    cal_header = [[Display(t, fg=green) for t in calendar.weekheader(3).split(' ')]]

    assert(len(cal_data[0]) == len(cal_header[0]))

    cells = [[self._render_monthcell(cell) for cell in row]
             for row in cal_data]

    month_name = Display('%s, %s' % (self.value.strftime('%B'), self.value.year))
    grid = Grid(cal_header + cells, align_right=True)

    return Vertical([month_name, grid])

  def on_event(self, ev):
    if ev.type == 'key':
      if ev.what == ord('t'):
        self.value = datetime.datetime.now()
        ev.stop()
      if ev.what == curses.KEY_LEFT:
        self.value += datetime.timedelta(days=-1)
        ev.stop()
      if ev.what == curses.KEY_RIGHT:
        self.value += datetime.timedelta(days=1)
        ev.stop()
      if ev.what == curses.KEY_UP:
        self.value += datetime.timedelta(weeks=-1)
        ev.stop()
      if ev.what == curses.KEY_DOWN:
        self.value += datetime.timedelta(weeks=1)
        ev.stop()


class Composite(Control):
  def __init__(self, controls, margin=0, **kwargs):
    super(Composite, self).__init__(**kwargs)
    self.controls = controls
    self.margin = margin

  def render(self, app):
    m = Display(' ' * self.margin)
    xs = [c.render(app) for c in self.controls]
    rendered = list(itertools.chain(*list(zip(xs, itertools.repeat(m)))))
    return Horizontal(rendered)

  def on_event(self, ev):
    propagate_focus(ev, self.controls, ev.app.layer(self),
                    [curses.KEY_LEFT, SHIFT_TAB],
                    [curses.KEY_RIGHT, curses.ascii.TAB])

  def _focus_order(self, key):
    """If we enter the control from the bottom, still focus the first element."""
    return (reversed
            if key in [curses.KEY_LEFT, SHIFT_TAB] else
            ident)


class Popup(Control):
  def __init__(self, inner, on_close, x=-1, y=-1, caption='', underscript='', **kwargs):
    super(Popup, self).__init__(**kwargs)
    self.x = x
    self.y = y
    self.inner = inner
    self.on_close = on_close
    self.caption = caption
    self.underscript = underscript

  def render(self, app):
    inner = Box(self.inner.render(app),
                x_fill=False,
                caption=Display(self.caption),
                underscript=Display(self.underscript))
    if self.x == -1 or self.y == -1:
      return Centered(inner)
    return Positioned(inner, x=self.x, y=self.y)

  def children(self):
    return [self.inner]

  def show(self, app):
    self.layer = app.push_layer(self)

  def on_event(self, ev):
    if ev.type == 'key':
      if ev.key == curses.ascii.ESC:
        self.layer.remove()
        ev.stop()
      if is_enter(ev):
        self.on_close(self, ev.app)
        self.layer.remove()
        ev.stop()


def EditPopup(app, on_close, value='', caption=''):
  Popup(Edit(value=value, min_size=30, fg=cyan), caption=caption, on_close=on_close).show(app)


class Combo(Control):
  def __init__(self, choices, index=0, **kwargs):
    super(Combo, self).__init__(**kwargs)
    self._choices = choices
    self.index = index
    self.can_focus = True
    self.last_combo = None

  def sanitize_index(self):
    self.index = min(max(0, self.index), len(self.choices) - 1)
    return 0 <= self.index < len(self.choices)

  @property
  def choices(self):
    if callable(self._choices):
      return self._choices()
    return self._choices

  @property
  def value(self):
    if not self.sanitize_index():
      return None
    return get_value(self.choices[self.index])

  @value.setter
  def value(self, value):
    try:
      self.index = max(0, self.choices.index(value))
    except ValueError:
      self.index = 0

  @property
  def caption(self):
    if not self.sanitize_index():
      return '-unset-'
    return str(self.choices[self.index])

  def render(self, app):
    attr = curses.A_STANDOUT if app.contains_focus(self) else 0
    self.last_combo = Display(self.caption, attr=attr)
    return self.last_combo

  def on_event(self, ev):
    if ev.type == 'key':
      if is_enter(ev):
        x = max(0, self.last_combo.rect.x - 2)
        y = max(0, self.last_combo.rect.y - 1)
        Popup(SelectList(self.choices, self.index), self.on_popup_close, x=x, y=y).show(ev.app)
        ev.stop()

  def on_popup_close(self, popup, app):
    self.index = popup.inner.index


class Toasty(Control):
  def __init__(self, text, duration=datetime.timedelta(seconds=3), border=True, **kwargs):
    super(Toasty, self).__init__(**kwargs)
    self.text = text
    self.duration = duration
    self.border = border

  def render(self, app):
    inner = Display(self.text, fg=self.fg)
    if self.border:
      inner = Box(inner, x_fill=False)
    return AlignRight(inner)

  def show(self, app):
    self.layer = app.push_layer(self, modal=False)
    app.enqueue(self.duration, self._done)

  def _done(self, app):
    self.layer.remove()


class DateCombo(Control):
  def __init__(self, value=None, **kwargs):
    super(DateCombo, self).__init__(**kwargs)
    self.value = value or datetime.datetime.now()
    self.can_focus = True

  @property
  def date(self):
    return self.value.date()

  def render(self, app):
    attr = curses.A_STANDOUT if app.contains_focus(self) else 0
    visual = self.value.strftime('%B %d, %Y')
    self.last_combo = Display(visual, attr=attr)
    return self.last_combo

  def on_event(self, ev):
    if ev.type == 'key':
      if is_enter(ev):
        x = max(0, self.last_combo.rect.x - 2)
        y = max(0, self.last_combo.rect.y - 1)
        Popup(SelectDate(self.value), self.on_popup_close, x=x, y=y).show(ev.app)

  def on_popup_close(self, popup, app):
    self.value = popup.inner.value


class Time(Composite):
  def __init__(self, value=None, **kwargs):
    self.value = value or datetime.datetime.utcnow().time()

    now_h = self.value.strftime('%H')
    now_m = '%02d' % (int(self.value.minute / 5) * 5)

    hours = ['%02d' % h for h in range(0, 24)]
    minutes = ['%02d' % m for m in range(0, 60, 5)]

    self.hour_combo = Combo(id='hour', choices=hours, index=hours.index(now_h))
    self.min_combo = Combo(id='min', choices=minutes, index=minutes.index(now_m))

    super(Time, self).__init__([
      self.hour_combo,
      Text(':'),
      self.min_combo,
      Text(' UTC')], **kwargs)

  @property
  def time(self):
    return datetime.time(int(self.hour_combo.value), int(self.min_combo.value))


class Edit(Control):
  """Standard text edit control.

  Arguments:
    highlight, fn: a syntax highlighting function. Will be given a string, and
      should return a list of curses (color, attributes), one for every
      character.
  """
  def __init__(self, value, min_size=0, highlight=None, **kwargs):
    super(Edit, self).__init__(**kwargs)
    self._value = value
    self.min_size = min_size
    self.can_focus = True
    self.cursor = len(value)
    self.highlight = highlight

  @property
  def value(self):
    return self._value

  @value.setter
  def value(self, value):
    self._value = value
    self.cursor = len(value)

  def render(self, app):
    focused = app.contains_focus(self)

    # Default highlighting, foreground color
    colorized = self.value
    if self.highlight:
      # Custom highlighting
      try:
        colorized = self.highlight(self.value)
      except Exception, e:
        logger.error(str(e))

    # Make the field longer for the cursor or display purposes
    ext_len = max(0, max(self.cursor + 1 if focused else 0, self.min_size) - len(self.value))
    colorized += ' ' * ext_len

    # Render that momma
    self.rendered = Horizontal(self._render_colorized(colorized, focused))
    return self.rendered

  def _render_colorized(self, colorized, focused):
    """Split a colorized string into Display() slices."""
    base_attr = 0
    if focused:
      base_attr = curses.A_UNDERLINE

    frag_list = []
    parts = colorized.split('\0')
    chars_so_far = 0
    for i in range(0, len(parts), 2):
      # i is regular, i+1 is colorized (if it's there)
      frag_list.append(Display(parts[i], fg=self.fg, attr=base_attr))
      if focused:
        chars_so_far = self._inject_cursor(chars_so_far, frag_list)

      if i + 1 < len(parts):
        color, attr, text = parts[i+1].split('\1')
        frag_list.append(Display(text, fg=int(color), attr=base_attr+int(attr)))
        if focused:
          chars_so_far = self._inject_cursor(chars_so_far, frag_list)

    return frag_list

  def _inject_cursor(self, chars_so_far, frag_list):
    """If the cursor falls into this fragment, highlight it."""
    last = frag_list[-1]
    if chars_so_far <= self.cursor < chars_so_far + len(last.text):
      offset = self.cursor - chars_so_far
      pre, hi, post = last.text[:offset], last.text[offset], last.text[offset+1:]
      frag_list[-1:] = [Display(pre, fg=last.fg, attr=last.attr),
                        Display(hi, fg=last.fg, attr=last.attr + curses.A_STANDOUT),
                        Display(post, fg=last.fg, attr=last.attr)]

    return chars_so_far + len(last.text)

  def on_event(self, ev):
    if ev.type == 'key':
      if ev.key in [CTRL_A, curses.KEY_HOME]:
        self.cursor = 0
        ev.stop()
      if ev.key in [CTRL_E, curses.KEY_END]:
        self.cursor = len(self._value)
        ev.stop()
      if ev.key in [curses.KEY_BACKSPACE, MAC_BACKSPACE]:
        if self.cursor > 0:
          self._value = self._value[:self.cursor-1] + self._value[self.cursor:]
          self.cursor = max(0, self.cursor - 1)
        ev.stop()
      elif ev.key == curses.ascii.DEL:
        if self.cursor < len(self._value) - 1:
          self._value = self._value[:self.cursor] + self._value[self.cursor+1:]
        ev.stop()
      if ev.key == curses.KEY_LEFT and self.cursor > 0:
        self.cursor -= 1
        ev.stop()
      if ev.key == curses.KEY_RIGHT and self.cursor < len(self._value):
        self.cursor += 1
        ev.stop()
      if 32 <= ev.key < 127:
        self._value = self._value[:self.cursor] + chr(ev.key) + self._value[self.cursor:]
        self.cursor += 1
        ev.stop()


class AutoCompleteEdit(Edit):
  def __init__(self, value, complete_fn, min_size=0, letters=string.letters, **kwargs):
    super(AutoCompleteEdit, self).__init__(value=value, min_size=min_size, **kwargs)
    self.complete_fn = complete_fn
    self.popup_visible = False
    self.select = SelectList([], 0, width=70, show_captions_at=30)
    self.popup = Popup(self.select, on_close=self.on_close, underscript='( ^N, ^P to move, Enter to select )')
    self.layer = None
    self.letters = letters

  def on_close(self):
    pass

  def show_popup(self, app, visible):
    if visible and not self.layer:
      self.popup.x = self.rendered.rect.x
      self.popup.y = self.rendered.rect.y + 1
      self.layer = app.push_layer(self.popup, modal=False)
    if not visible and self.layer:
      self.layer.remove()
      self.layer = None

  def set_autocomplete_options(self, options):
    self.select.choices = options

  @property
  def cursor_word(self):
    """Return the word under the cursor.

    Returns (offset, string).
    """
    i = min(self.cursor, len(self.value) - 1)  # Inclusive
    while (i > 0 and self.value[i] in self.letters and
           self.value[i-1] in self.letters):
      i -= 1
    j = i + 1  # Exclusive
    while (j < len(self.value) and self.value[j] in self.letters):
      j += 1
    return (i, self.value[i:j])

  def replace_cursor_word(self, word):
    i, current = self.cursor_word
    self.value = self.value[:i] + word + self.value[i+len(current):]

  def on_event(self, ev):
    super(AutoCompleteEdit, self).on_event(ev)

    if ev.app.contains_focus(self):
      _, word = self.cursor_word
      self.set_autocomplete_options(self.complete_fn(word))
      interesting = (len(self.select.choices) > 1
                     or (len(self.select.choices) == 1) and self.select.choices[0] != word)
      self.show_popup(ev.app, interesting)
    if ev.type == 'blur':
      self.show_popup(ev.app, False)

    if ev.type == 'key' and self.layer:
      if ev.key in [CTRL_J, CTRL_N]:
        self.select.adjust(1)
        ev.stop()
      if ev.key in [CTRL_K, CTRL_P]:
        self.select.adjust(-1)
        ev.stop()
      if is_enter(ev):
        self.replace_cursor_word(self.select.value)
        self.show_popup(ev.app, False)
        ev.stop()
      if ev.key in [curses.ascii.ESC]:
        self.show_popup(ev.app, False)
        ev.stop()


class Button(Control):
  def __init__(self, caption, on_click=None, fg=yellow, **kwargs):
    super(Button, self).__init__(fg=fg, **kwargs)
    self.caption = caption
    self.on_click = on_click
    self.can_focus = True

  def render(self, app):
    return Display('[ %s ]' % self.caption, fg=self.fg,
                   attr=curses.A_STANDOUT if app.contains_focus(self) else 0)

  def on_event(self, ev):
    if ev.type == 'key':
      if is_enter(ev) or ev.what == ord(' '):
        if self.on_click:
          self.on_click(ev.app)
          ev.stop()


class PreviewPane(Control):
  def __init__(self, lines, row_selectable=False, on_select_row=None, **kwargs):
    super(PreviewPane, self).__init__(**kwargs)
    self.lines = lines
    self.can_focus = True
    self.v_scroll_offset = 0
    self.h_scroll_offset = 0
    self.app = None
    self.row_selectable = row_selectable
    self.selected_row = 0
    self.on_select_row = on_select_row

  def render(self, app):
    self.app = app  # FIXME: That's nasty
    attr = 0
    focused = app.contains_focus(self)
    if focused:
      attr = curses.A_BOLD

    display = (l[self.h_scroll_offset:] for l in self.lines[self.v_scroll_offset:])
    if self.row_selectable and focused:
      hi_offset = self.selected_row - self.v_scroll_offset
      self.last_render = Vertical([
        Display(line, attr=attr + (curses.A_STANDOUT if i == hi_offset else 0)) for i, line in enumerate(display)
        ])
    else:
      self.last_render = Display('\n'.join(display), attr=attr)
    return self.last_render

  def on_event(self, ev):
    if ev.type == 'key':
      v_scrolls = {
          curses.KEY_UP:     -1,
          ord('k'):          -1,
          curses.KEY_PPAGE: -30,
          curses.KEY_DOWN:    1,
          ord('j'):           1,
          curses.KEY_NPAGE:  30,
          curses.KEY_HOME:  -9999999999,
          ord('g'):         -9999999999,
          curses.KEY_END:    9999999999,
          ord('G'):          9999999999,
          }
      h_scrolls = {
          curses.KEY_LEFT: -10,
          ord('h'): -10,
          curses.KEY_RIGHT: 10,
          ord('k'): 10,
          }

      if ev.key in v_scrolls:
        if self.row_selectable:
          # We scroll the focus instead of the screen
          new_selected_row = max(0, min(self.selected_row + v_scrolls[ev.key], len(self.lines) - 1))
          if self.selected_row != new_selected_row:
            self.selected_row = new_selected_row
            self.v_scroll_offset = min(self.v_scroll_offset, self.selected_row)
            self.v_scroll_offset = max(self.v_scroll_offset, self.selected_row - self.last_render.rect.h + 1)
            ev.stop()
        else:
          # We scroll the screen
          new_v_scroll_offset = max(0, min(self.v_scroll_offset + v_scrolls[ev.key], len(self.lines) - self.last_render.rect.h))
          if new_v_scroll_offset != self.v_scroll_offset:
            self.v_scroll_offset = new_v_scroll_offset
            ev.stop()

      if ev.key in h_scrolls:
        new_h_scroll_offset = max(0, self.h_scroll_offset + h_scrolls[ev.key])
        if new_h_scroll_offset != self.h_scroll_offset:
          self.h_scroll_offset = new_h_scroll_offset
          ev.stop()

      if ev.key == ord('s'):
        EditPopup(ev.app, self._save_contents, value='report.log', caption='Save to file')
      if is_enter(ev) and self.row_selectable and self.on_select_row and 0 <= self.row_selectable < len(self.lines):
        self.on_select_row(self.lines[self.selected_row], ev.app)
        ev.stop()

  def _save_contents(self, accept, box):
    if not accept:
      return
    filename = box.inner.value

    try:
      with file(filename, 'w') as f:
        f.write('\n'.join(self.lines))
      Toasty('%s saved' % filename).show(self.app)
    except Exception, e:
      Toasty(str(e), duration=datetime.timedelta(seconds=5)).show(self.app)


#----------------------------------------------------------------------
#  FRAMEWORK classes


class Rect(object):
  def __init__(self, app, screen, x, y, w, h):
    self.app = app
    self.screen = screen
    self.x = x
    self.y = y
    self.w = w
    self.h = h

  def get_color(self, fg, bg):
    return self.app.get_color(fg, bg)

  def adj_rect(self, dx, dy, dw=0, dh=0):
    return self.sub_rect(dx, dy, self.w - dx - dw, self.h - dy - dh)

  def sub_rect(self, dx, dy, w, h):
    return Rect(self.app, self.screen, self.x + dx, self.y + dy, w, h)

  def resize(self, w, h):
    return self.sub_rect(0, 0, w, h)

  def clear(self):
    line = ' ' * self.w
    for j in range(self.y, self.y + self.h):
      self.screen.addstr(j, self.x, line)

  def __repr__(self):
    return '(%s,%s,%s,%s)' % (self.x, self.y, self.w, self.h)


class Event(object):
  def __init__(self, type, what, target, app):
    self.type = type
    self.key = what
    self.what = what
    self.target = target
    self.last = None
    self.propagating = True
    self.app = app

  def stop(self):
    self.propagating = False


def object_tree(root):
  stack = [(None, root)]
  while stack:
    parent, obj = stack.pop()
    yield parent, obj
    children = obj.children()
    stack.extend((obj, c) for c in reversed(children))


class Layer(Control):
  """A layer in the app, modal or non-modal.

  Non-modal layers stack, but can't be interacted with. The topmost modal layer
  will be the one receiving input.
  """

  def __init__(self, root, app, modal, id):
    super(Layer, self).__init__()
    self.root = root
    self.focused = self.root
    self.app = app
    self.modal = modal
    self.id = id

    self._focus_first()

  def _focus_first(self):
    for parent, child in object_tree(self):
      if child.can_focus:
        self.focus(child)
        return

  def _focus_last(self):
    controls = list(object_tree(self))
    controls.reverse()
    for parent, child in controls:
      if child.can_focus:
        self.focus(child)
        return

  def focus(self, ctrl):
    assert(ctrl.can_focus)
    self.focused.on_event(Event('blur', None, self.focused, self.app))
    self.focused = ctrl
    self.focused.on_event(Event('focus', None, self.focused, self.app))

  def children(self):
    return [self.root]

  def render(self, app):
    return self.root.render(app)


class TimerHandle(object):
  def __init__(self, app, timer_id):
    self.app = app
    self.timer_id = timer_id

  def cancel(self):
    for i, (_, _, timer_id) in enumerate(self.app.timers):
      if timer_id == self.timer_id:
        self.app.timers.pop(i)
        break


class LayerHandle(object):
  def __init__(self, app, layer_id):
    self.app = app
    self.layer_id = layer_id

  def remove(self):
    for i, layer in enumerate(self.app.layers):
      if layer.id == self.layer_id:
        self.app.layers.pop(i)
        break


class App(Control):
  def __init__(self, root):
    super(App, self).__init__()
    self.exit = False
    self.screen = None
    self.layers = []
    self.color_cache = {}
    self.color_counter = 1
    self.timers = []
    self.uniq_id = 0

    self.push_layer(root)

  def enqueue(self, delta, on_time):
    deadline = datetime.datetime.now() + delta
    self.uniq_id += 1
    self.timers.append((deadline, on_time, self.uniq_id))
    self.timers.sort()
    return TimerHandle(self, self.uniq_id)

  @property
  def active_layer(self):
    # Return the highest modal layer
    for l in reversed(self.layers):
      if l.modal:
        return l
    assert(False)

  def push_layer(self, control, modal=True):
    assert(isinstance(control, Control))
    self.uniq_id += 1
    self.layers.append(Layer(control, self, modal, self.uniq_id))
    return LayerHandle(self, self.uniq_id)

  def _all_objects(self):
    return object_tree(self)

  def children(self):
    return self.layers

  def get_parent(self, ctrl):
    for parent, child in self._all_objects():
      if child is ctrl:
        return parent
    return None

  def contains_focus(self, ctrl):
    return self.find_ancestor(self.active_layer.focused, [ctrl]) is not None

  def find_ancestor(self, ctrl, set):
    """Find parent from a set of parents."""
    while ctrl:
      if ctrl in set:
        return ctrl
      ctrl = self.get_parent(ctrl)

  def layer(self, ctrl):
    return self.find_ancestor(ctrl, self.layers)

  def get_color(self, fore, back):
    tup = (fore, back)
    if tup not in self.color_cache:
      curses.init_pair(self.color_counter, fore, back)
      self.color_cache[tup] = self.color_counter
      self.color_counter += 1
    return self.color_cache[tup]

  @property
  def ch_wait_time(self):
    if self.timers:
      # Time until next timer
      return max(0, int((self.timers[0][0] - datetime.datetime.now()).total_seconds() * 1000))
    # Indefinite wait
    return -1

  def fire_timers(self):
    now = datetime.datetime.now()
    while self.timers and self.timers[0][0] <= now:
      _, on_time, _ = self.timers.pop(0)
      on_time(self)

  def run(self, screen):
    curses.nonl()  # We need Ctrl-J!
    curses.curs_set(0)
    self.screen = screen
    while not self.exit:
      self.update()
      self.screen.timeout(self.ch_wait_time)
      try:
        c = self.screen.getch()
        if c != -1:
          self.dispatch_event(Event('key', c, self.active_layer.focused, self))
      except KeyboardInterrupt:
        # Just another kind of event
        self.dispatch_event(Event('break', None, self.active_layer.focused, self))
      self.fire_timers()

  def update(self):
    h, w = self.screen.getmaxyx()

    self.screen.erase()
    for layer in self.layers:
      view = layer.render(self)
      view.display(Rect(self, self.screen, 0, 0, w, h))
    self.screen.refresh()

  def dispatch_event(self, ev):
    tgt = ev.target
    while tgt and ev.propagating:
      tgt.on_event(ev)
      ev.last = tgt
      tgt = self.get_parent(tgt)

  def on_event(self, ev):
    if ev.type == 'break':
      # If the break got here, re-raise it
      raise KeyboardInterrupt()

    if ev.type == 'key':
      if ev.key in [curses.ascii.ESC]:
        self.exit = True
        ev.stop()

      # If we got here with focus-shifting, set focus back to the first control
      if ev.key in [curses.KEY_DOWN, curses.ascii.TAB]:
        self.active_layer._focus_first()
      if ev.key in [curses.KEY_UP, SHIFT_TAB]:
        self.active_layer._focus_last()

  def find(self, id):
    for parent, child in object_tree(self):
      if child.id == id:
        return child
    raise RuntimeError('No such control: %s' % id)


def get_all(root, ids):
  ret = {}
  for id in ids:
    obj = root.find(id)
    if hasattr(obj, 'value'):
      ret[id] = obj.value
  return ret


def set_all(root, dct):
  for id, value in dct.iteritems():
    try:
      obj = root.find(id)
      if hasattr(obj, 'value'):
        obj.value = value
    except RuntimeError:
      pass


def walk(root):
  reduce_esc_delay()
  curses.wrapper(App(root).run)
