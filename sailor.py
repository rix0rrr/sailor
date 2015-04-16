import calendar
import curses
import curses.ascii
from curses import textpad
import datetime
import logging
import os
import itertools

logger = logging.getLogger('sailor')

CTRL_A = 1
CTRL_E = 5
MAC_BACKSPACE = 127   # Don't feel like finding out why
ALT_ENTER = 10 # Don't feel like finding out why
SHIFT_TAB = 353

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
  return ev.key in [curses.KEY_ENTER, ALT_ENTER]


def ident(x):
  return x

#----------------------------------------------------------------------
#  VIEW classes

class View(object):
  def size(self, rect):
    return (0, 0)

  def display(self, rect):
    self.rect = rect
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

  def size(self, rect):
    return max(self.min_width, max(len(l) for l in self.lines)), len(self.lines)

  def disp(self, rect):
    col = rect.get_color(self.fg, self.bg)
    print_width = max(0, rect.w)
    lines = self.lines[:rect.h]
    if print_width > 0 and lines:
      for i, line in enumerate(lines):
        rect.screen.addstr(rect.y + i, rect.x, line[:print_width], curses.color_pair(col) | self.attr)


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
    return sum(widths) + max(len(self.views) - 1, 0) * self.margin, max(heights)

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
    return max(widths), sum(heights) + max(len(self.views) - 1, 0) * self.margin

  def disp(self, rect):
    for v in self.views:
      v.display(rect)
      dy = v.size(rect)[1] + self.margin
      rect = rect.adj_rect(0, dy)


class FloatingWindow(View):
  def __init__(self, inner, x=-1, y=-1):
    self.inner = inner
    self.x = x
    self.y = y

  def size(self, rect):
    return self.inner.size(rect)

  def disp(self, rect):
    size = self.size(rect)
    irect = Rect(rect.app, rect.screen, self.x, self.y, size[0], size[1])
    irect.clear()
    self.inner.display(irect)


class Box(View):
  def __init__(self, inner, caption=None, x_margin=1, y_margin=0, x_fill=True, y_fill=False):
    self.inner = inner
    self.caption = caption
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

      textpad.rectangle(rect.screen, rect.y, rect.x, y1, x1)
      if self.caption:
        self.caption.display(rect.adj_rect(3, 0))
      self.inner.display(rect.adj_rect(1 + self.x_margin, 1 + self.y_margin, 1 + self.x_margin, 1 + self.y_margin))


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
        if 0 <= i < len(controls) and layer.focus(controls[i], backwards=back):
          ev.stop()
          return True
  return False


class Panel(Control):
  def __init__(self, controls, caption=None, **kwargs):
    super(Panel, self).__init__(**kwargs)
    self.controls = controls
    self.caption = caption

  def render(self, app):
    return Box(Vertical([c.render(app) for c in self.controls]),
               caption=self.caption.render(app) if self.caption else None)

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
  def __init__(self, choices, index, width=30, height=10, **kwargs):
    super(SelectList, self).__init__(**kwargs)
    self.choices = choices
    self.index = index
    self.width = width
    self.height = height
    self.scroll_offset = max(0, min(self.index, len(self.choices) - height))
    self.can_focus = True

  @property
  def value(self):
    return self.choices[self.index]

  def render(self, app):
    lines = self.choices[self.scroll_offset:self.scroll_offset + self.height]
    lines.extend([''] * (self.height - len(lines)))
    i_hi = self.index - self.scroll_offset

    vert = Vertical([Display(l, min_width=self.width) for l in lines[:i_hi]] +
                    [Display(lines[i_hi], min_width=self.width, attr=curses.A_STANDOUT)] +
                    [Display(l, min_width=self.width) for l in lines[i_hi+1:]])
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

class Popup(Control):
  def __init__(self, x, y, inner, on_close, caption='', **kwargs):
    super(Popup, self).__init__(**kwargs)
    self.x = x
    self.y = y
    self.inner = inner
    self.on_close = on_close
    self.caption = caption

  def render(self, app):
    return FloatingWindow(Box(self.inner.render(app),
                              x_fill=False,
                              caption=Display(self.caption)),
                          x=self.x,
                          y=self.y)

  def children(self):
    return [self.inner]

  def show(self, app):
    app.push_layer(self)

  def on_event(self, ev):
    if ev.type == 'key':
      if ev.key == curses.ascii.ESC:
        self.on_close(False, self)
        ev.app.pop_layer()
      if is_enter(ev):
        self.on_close(True, self)
        ev.app.pop_layer()


class Combo(Control):
  def __init__(self, choices, index=0, **kwargs):
    super(Combo, self).__init__(**kwargs)
    self.choices = choices
    self.index = index
    self.can_focus = True
    self.last_combo = None

  @property
  def value(self):
    return self.choices[self.index]

  def render(self, app):
    attr = curses.A_STANDOUT if app.contains_focus(self) else 0
    self.last_combo = Display(self.value, attr=attr)
    return self.last_combo

  def on_event(self, ev):
    if ev.type == 'key':
      if is_enter(ev):
        x = max(0, self.last_combo.rect.x - 2)
        y = max(0, self.last_combo.rect.y - 1)
        Popup(x, y, SelectList(self.choices, self.index), self.on_popup_close).show(ev.app)

  def on_popup_close(self, success, popup):
    if success:
      self.index = popup.inner.index


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
        Popup(x, y, SelectDate(self.value), self.on_popup_close).show(ev.app)

  def on_popup_close(self, success, popup):
    if success:
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
  def __init__(self, value, **kwargs):
    super(Edit, self).__init__(**kwargs)
    self.value = value
    self.can_focus = True
    self.cursor = len(value)

  def render(self, app):
    if app.contains_focus(self):
      hi = self.value[self.cursor] if self.cursor < len(self.value) else ' '
      return Horizontal([Display(self.value[:self.cursor], fg=self.fg, attr=curses.A_UNDERLINE),
                         Display(hi, fg=self.fg, attr=curses.A_REVERSE),
                         Display(self.value[self.cursor+1:], fg=self.fg, attr=curses.A_UNDERLINE),
                         ])
    else:
      return Display(self.value, fg=self.fg)

  def on_event(self, ev):
    if ev.type == 'key':
      if ev.key in [CTRL_A, curses.KEY_HOME]:
        self.cursor = 0
        ev.stop()
      if ev.key in [CTRL_E, curses.KEY_END]:
        self.cursor = len(self.value)
        ev.stop()
      if ev.key in [curses.KEY_BACKSPACE, MAC_BACKSPACE]:
        self.value = self.value[:self.cursor-1] + self.value[self.cursor:]
        self.cursor = max(0, self.cursor - 1)
        ev.stop()
      if ev.key == curses.ascii.DEL:
        self.value = self.value[:self.cursor] + self.value[self.cursor+1:]
        ev.stop()
      if ev.key == curses.KEY_LEFT and self.cursor > 0:
        self.cursor -= 1
        ev.stop()
      if ev.key == curses.KEY_RIGHT and self.cursor < len(self.value):
        self.cursor += 1
        ev.stop()
      if is_enter(ev):
        ev.key = curses.ascii.TAB
      if 32 <= ev.key < 127:
        self.value = self.value[:self.cursor] + chr(ev.key) + self.value[self.cursor:]
        self.cursor += 1
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
  def __init__(self, lines, **kwargs):
    super(PreviewPane, self).__init__(**kwargs)
    self.lines = lines
    self.can_focus = True
    self.v_scroll_offset = 0
    self.h_scroll_offset = 0

  def render(self, app):
    attr = 0
    if app.contains_focus(self):
      attr = curses.A_BOLD

    display = (l[self.h_scroll_offset:] for l in self.lines[self.v_scroll_offset:])
    self.last_render = Display('\n'.join(display), attr=attr)
    return self.last_render

  def on_event(self, ev):
    if ev.type == 'key':
      v_scrolls = {
          curses.KEY_UP: -1,
          ord('k'): -1,
          curses.KEY_PPAGE: -30,
          curses.KEY_DOWN: 1,
          ord('j'): 1,
          curses.KEY_NPAGE: 30,
          }
      h_scrolls = {
          curses.KEY_LEFT: -10,
          ord('h'): -10,
          curses.KEY_RIGHT: 10,
          ord('k'): 10,
          }

      if ev.key in v_scrolls:
        new_v_scroll_offset = max(0, min(self.v_scroll_offset + v_scrolls[ev.key], len(self.lines) - self.last_render.rect.h))
        if new_v_scroll_offset != self.v_scroll_offset:
          self.v_scroll_offset = new_v_scroll_offset
          ev.stop()

      if ev.key in h_scrolls:
        new_h_scroll_offset = max(0, self.h_scroll_offset + h_scrolls[ev.key])
        if new_h_scroll_offset != self.h_scroll_offset:
          self.h_scroll_offset = new_h_scroll_offset
          ev.stop()


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
  """A modal layer in the app."""

  def __init__(self, root, app):
    super(Layer, self).__init__()
    self.root = root
    self.focused = self.root
    self.app = app

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

  def focus(self, ctrl, backwards=False):
    if ctrl.can_focus:
      self.focused.on_event(Event('blur', None, self.focused, self.app))
      self.focused = ctrl
      self.focused.on_event(Event('focus', None, self.focused, self.app))
      return True

    order = reversed if backwards else ident

    for child in order(ctrl.children()):
      if self.focus(child, backwards=backwards):
        return True
    return False

  def children(self):
    return [self.root]

  def render(self, app):
    return self.root.render(app)


class App(Control):
  def __init__(self, root):
    super(App, self).__init__()
    self.exit = False
    self.screen = None
    self.layers = []
    self.color_cache = {}
    self.color_counter = 1
    self.push_layer(root)
    self.timers = []

  def enqueue(self, delta, on_time):
    deadline = datetime.datetime.now() + delta
    self.timers.append((deadline, on_time))
    self.timers.sort()

  @property
  def active_layer(self):
    return self.layers[-1]

  def push_layer(self, control):
    self.layers.append(Layer(control, self))

  def pop_layer(self):
    self.layers.pop()

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
      _, on_time = self.timers.pop(0)
      on_time(self)

  def run(self, screen):
    curses.curs_set(0)
    self.screen = screen
    while not self.exit:
      self.update()
      self.screen.timeout(self.ch_wait_time)
      c = self.screen.getch()
      if c != -1:
        self.dispatch_event(Event('key', c, self.active_layer.focused, self))
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


def walk(root):
  reduce_esc_delay()
  curses.wrapper(App(root).run)
