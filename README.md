sailor, yet another curses widget library
=========================================

I didn't like npyscreen and Urwid, so I made an ncurses widget library.

* npyscreen looks great, but I don't like the way it uses classes and
  object-oriented programming. It's very hard to make composite widgets and
  complex layout from simple building blocks (i.e., without having to implement
  a bunch of custom classes)

* Urwid looks gaudy, and more low-level than what I want.

Sailor fills the gap that I saw in this space.

For users
---------

One control is the root of your GUI application. It is continuously rendered
until the application exits.

Some controls, such as `Button`s, have event handers. The argument to an event
handler always includes a built-in `app` object. You exit the GUI loop by
setting `app.exit = True`.

Start the GUI loop by calling `sailor.walk(root_control)`.

Example:

```python
def do_exit(app):
  app.exit = True

root = s.Panel(
  caption=s.Text('Hello World'),
  controls=[
    s.Text('This just shows you some text in a bordered panel.'),
    s.Text('Hit the button below to quit.'),
    s.Button('Exit', on_click=do_exit)
  ])

s.walk(root)
```

Since there is only ever one control that is the root control, to do interesting
things you need to make this top-level control either a control that contains
multiple other controls (`Panel`), a control that contains a single other
control but which one that is can change (`SwitchableControl`), or generate
`Popup` controls in response to events.

### Available controls

* `Text(string, [fg], [bg])`: display some literal text.
* `Edit(string, [min_size], [highlight])`: text edit control. `highlight`
  can be a function to syntax highlight the entered text. See the source
  for info :)
* `AutoCompleteEdit(string, complete_fn, [min_size])`: like edit, but
  has a funciton that takes the current word and returns all possible
  completions.
* `Button(string, [on_click])`: A bog-standard button.
* `Panel(controls, [caption], [underscript])`: vertically contains other
  controls, surrounded by a box.
* `Labeled(string, control)`: puts a label to the left of the control.
* `SelectList(options, [index], [width], [height])`: shows a selection list.
  The selected value is available in `.value`.
* `Combo(options, [index])`: a SelectList in a popup.
* `SelectDate(value)`: shows a day calendar. `.value` is in datetime format,
  `.date` in date.
* `Popup(control, on_close).show(app)`: show a modal popup that contains another
  control.  The popup is automatically removed when an ENTER or ESC keypress
  escapes the focused control, but `on_close(popup, app)` will only be called if
  ENTER was used to remove the popup.
* `Time(value)`: a time selection control. `.time` has the selected time.
* `Stacked(controls)`: vertically contains other controls, no decoration.
* `PreviewPane(lines, [row_selectable], [on_select_row])`: a scrollable panel
  to display a large document in.
* `SwitchableControl(initial_control)`: control that can switch what
  control it's displaying.

Impression:

```
┌──Control showcase───────────────────────────────────────────────────────────┐
│ Text            This is plain text in a different color                     │
│ Panel           ┌─────────────────────────────────────────────────────────┐ │
│                 │ Inner panel just because we can                         │ │
│                 └─────────────────────────────────────────────────────────┘ │
│ SelectList      option 3                                                    │
│                 option 4                                                    │
│                 option 5                                                    │
│ Combo           option 1                                                    │
│ DateCombo       July 11, 2018                                               │
│ Time            19:15 UTC                                                   │
│ Popup           [ Hit me ]                                                  │
│ Edit            you can edit this                                           │
│ AutoComplete    type here                                                   │
│ SwitchableCtrl  Switchable 1                                                │
│                 [ Next ]                                                    │
│ Button          [ ┌────────────────────────────────────┐                    │
└───────────────────│ Just a popup to show you something │────────────────────┘
                    └────────────────────────────────────┘
```

For control authors
-------------------

As a user of `sailor`, you might want to build your own higher-level
controls out of lower-level building blocks. This section might also
be interesting to you.

```
                          can contain
                           multiple
 ┌───────────────┐          ┌───┐
 │               │          │   │
 │               ▼          │   ▼
 │  continuously       ┌────┴────────┐              ┌──────────────┐
 │  render root        │             │  renders to  │              │
 │    control          │   Control   ├─────────────▶│     View     │
 │   ─────────────────▶│             │              │              │
 │               │     └─────────────┘              └──────────────┘
 │               │      manages state                renders to screen
 └───────────────┘

sailor.walk(control)    EXAMPLES                     EXAMPLES

                        Button                       Display
                        Edit                         Box
                        Combo                        Centered
                        Panel                        HFill
                        Date                         ...
                        Time
```

Sailor consists of `Control`s. Some controls have _values_ (such as a text edit
field). Other controls (such as a `Panel`) only exist to contain other controls
and lay them out in a certain way.

Controls have a way to render themselves. The result of rendering a control is
a `View`. No painting has been done at this point, a view is just another
object. Finally, a view is asked to render itself to an ncurses screen, which
can entail painting characters, rendering subviews, or both. Examples of view
objects are horizontal or vertical layouts, a piece of text, or a box.

The advantage of separating `Control`s and `View`s is that the control doesn't
have to bother with the low-level details of painting. It deals with state
management and can generally just return a convenient display representation of
itself using the `View` primitives, which will automatically lay themselves
out in convenient way.

The overarching philosophy is that in sailor, you work at the object-level,
piecing together objects to do what you want, as opposed to inheriting and
overriding classes. It works very much in "immediate mode", like React, where
all controls paint themselves to the screen on every frame, and the framework
makes sure that updates are done efficiently.

We don't use any of the facilities of ncurses like windows and pads. These
serve a similar purpose to what sailor does by itself, but more dynamically
(controls can easily resize itself in sailor).  Efficiently updating the
terminal by doing a diff of two screen states is the purpose of the standard
curses library, so sailor doesn't need to take care to be efficient.

### Controls

We do have _some_ inheritance. Controls inherit from `Control`. Controls are
supposed to do the following things:

* Set `self.can_focus` if the control can receive focus.
* Implement `children()` if the control has subcontrols.
* Implement `render(app)` to return the view of the control.
* Implement `on_event(event)` to handle events.

There are a bunch of default controls already:

* `Text`
* `Edit`
* `Panel`
* `Labeled`
* `SelectList`
* `Combo`
* `Composite`
* `Popup`
* `SelectDate`
* `DateCombo`

### Views

Views are used to render characters to the screen or laying out other views.
You should rarely need to implement new View classes, but if you want to, a
View needs to:

* Implement `size(parent_rect)`, returning the size needed for the view given
  the rect to work in.
* Implement `disp(parent_rect)`, render (using ncurses routines) in the given
  rect (same as passed to `size()`).

Available Views are:

* `Display`
* `HFill`
* `Horizontal`, `Vertical`
* `Grid`
* `Box`
* `FloatingWindow`
