from __future__ import print_function
import os
import sublime
import sublime_plugin
import subprocess
import sys
import time
import threading

SETTINGS = None


def plugin_loaded():
  global SETTINGS
  SETTINGS = sublime.load_settings('PyCover.sublime-settings')
  if SETTINGS and SETTINGS.get('python') is not None:
    print('Loaded settings for PyCover')
  else:
    print('Error loading settings for PyCover')

if sys.version_info[0] == 2:
  sublime.set_timeout(plugin_loaded, 0)


class SublimePythonCoverageListener(sublime_plugin.EventListener):
  """Event listener to highlight uncovered lines when a Python file loads."""

  def on_load(self, view):
    if SETTINGS.get('onload', False) and 'source.python' in view.scope_name(0):
      view.run_command('show_python_coverage')


class ShowPythonCoverageCommand(sublime_plugin.TextCommand):
  """Highlight uncovered lines in the current file
  based on a previous coverage run."""

  def is_visible(self):
    return self.is_enabled()

  def is_enabled(self):
    return 'source.python' in self.view.scope_name(0)

  def run(self, edit):
    fname = self.view.file_name()
    if not self.is_enabled() or not fname:
      return

    local_settings = self.view.settings()
    if local_settings.get('showing', False):
      self.view.erase_regions('PyCover')
      local_settings.set('showing', False)
      return  # Toggle off

    cov_file = find(fname, '.coverage')
    if not cov_file:
      status_report('Could not find .coverage file for %s' % fname, wrap=True)
      return
    cov_config = find(fname, '.coveragerc') or ''

    # run missing_lines.py with the correct paths
    python = SETTINGS.get('python', '')
    if not python:
      python = which('python')
    ml_file = os.path.join(sublime.packages_path(), 'PyCover', 'scripts',
                           'missing_lines.py')
    p = subprocess.Popen([python, ml_file, cov_file, cov_config, fname],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    threading.Thread(target=missing_lines_callback, args=(self.view, p)).start()


def missing_lines_callback(view, proc, poll_sleep=0.1, poll_timeout=10):
  progress_status = lambda: sublime.status_message('Finding missing lines...')
  sublime.set_timeout(progress_status, 0)
  # poll for results
  tic = time.time()
  while proc.poll() is None:
    if time.time() - tic > poll_timeout:
      msg = 'missing_lines.py timed out after %f s' % (time.time() - tic)
      status_report(msg, wrap=True)
      proc.kill()
      return
    time.sleep(poll_sleep)
    sublime.set_timeout(progress_status, 0)

  stdout, stderr = proc.communicate()
  if proc.returncode != 0:
    status_report(stderr.decode('UTF-8'), wrap=True)
    return

  # read stdout to parse missing lines
  missing_lines = map(int, stdout.decode('UTF-8').splitlines())

  # update highlighted regions
  sublime.set_timeout(lambda: _update_highlighted(view, missing_lines), 0)


def _update_highlighted(view, missing_lines):
  outlines = [
      view.full_line(view.text_point(line_num-1, 0))
      for line_num in missing_lines]
  view.erase_regions('PyCover')

  flags = sublime.HIDDEN
  if SETTINGS.get('highlight_uncovered_lines', False):
    flags = sublime.DRAW_NO_OUTLINE

  if outlines:
    view.add_regions('PyCover', outlines, 'invalid',
                     'Packages/PyCover/themes/default/bar.png', flags)
    view.settings().set('showing', True)
  status_report('%d missing lines annotated.' % len(outlines))


def find(base, *rel, **kwargs):
  access = kwargs.get('access', os.R_OK)
  rel = os.path.join(*rel)
  while True:
    path = os.path.join(base, rel)
    if os.access(path, access):
      return path
    baseprev, base = base, os.path.dirname(base)
    if not base or base == baseprev:
      return


def which(progname):
  exts = os.environ.get('PATHEXT', '').split(os.pathsep)
  for path in os.environ['PATH'].split(os.pathsep):
    for ext in exts:
      fullpath = os.path.join(path, progname + ext)
      if os.path.exists(fullpath):
        return fullpath
  return None


def status_report(message, wrap=False):
  print('PyCover:', message)
  if wrap:
    sublime.set_timeout(lambda: sublime.status_message(message), 0)
  else:
    sublime.status_message(message)
