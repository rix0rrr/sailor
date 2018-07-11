"""Sample sailor program."""
# Load sailor from one directory higher
import sys
sys.path.insert(0, '..')

import sailor as s

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
