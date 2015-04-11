"""Sample sailor program."""

import datetime

import sailor as s


now = datetime.datetime.now()
now_h = now.strftime('%H')
now_m = '%02d' % ((int(now.strftime('%M')) / 5) * 5)

hours = ['%02d' % h for h in range(0, 24)]
minutes = ['%02d' % m for m in range(0, 60, 5)]


def do_exit(app):
  app.exit = True


panel = s.Panel(caption=s.Text('sailor is awesome'), controls=[
  s.Labeled('Edit', s.Edit('Type here', id='edit')),
  s.Labeled('Combo', s.Combo(['Choice 1', 'Choice 2', 'Choice 3'], id='choice')),
  s.Labeled('Date', s.DateCombo(id='date')),
  s.Labeled('Time', s.Composite([
        s.Combo(choices=hours, index=hours.index(now_h), id='hour'),
        s.Text(':'),
        s.Combo(choices=minutes, index=minutes.index(now_m), id='min')])),
  s.Labeled('Where', s.Composite([
        s.Edit('Candles', id='field'),
        s.Combo(['>=', '<=', '==', 'eq', 'ne'], id='op'),
        s.Edit('500', id='val'),
        ], margin=1)),
  s.Labeled('', s.Button('Exit', on_click=do_exit)),
  ])

s.walk(panel)

print('Date/Time: %s %s:%s' % (panel.find('date').value.date(), panel.find('hour').value, panel.find('min').value))
print('Combo:     %s' % panel.find('choice').value)
print('Edit:      %s' % panel.find('edit').value)
print('Field:     %s' % panel.find('field').value)
print('Operation: %s' % panel.find('op').value)
print('Value:     %s' % panel.find('val').value)
