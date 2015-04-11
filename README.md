sailor, yet another curses widget library
=========================================

I didn't like npyscreen and Urwid, so I made an ncurses widget library.

* npyscreen looks great, but I don't like the way it uses classes and
  object-oriented programming. It's very hard to make composite widgets and
  complex layout from simple building blocks (i.e., without having to implement
  a bunch of custom classes)

* Urwid looks gaudy, and more low-level than what I want.

Sailor fills the gap that I saw in this space.

Philosophy
----------

Sailor consists of _controls_. Some controls have _values_ (such as a text edit
field). Other controls (such as a Panel) only exist to contain other controls
and lay them out in a certain way.

Controls have a way to render themselves. The result of rendering a control is
a _view_. No painting has been done at this point, a view is just another
object. Finally, a view is asked to render itself to an ncurses screen, which
can entail painting characters, rendering subviews, or both. Examples of view
objects are horizontal or vertical layouts, a piece of text, or a box.

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

Controls
--------

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

Views
-----

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
