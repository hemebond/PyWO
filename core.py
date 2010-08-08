#
# Copyright 2010, Wojciech 'KosciaK' Pietrzok
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import time
import threading

from Xlib import X, XK, Xatom, protocol
from Xlib.display import Display


__author__ = "Wojciech 'KosciaK' Pietrzok <kosciak@kosciak.net>"


class Gravity(object):

    """Gravity point as a percentage of width and height of the window."""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.is_middle = (x == 1.0/2) and (y == 1.0/2)


    @property
    def is_top(self):
        """Return True if gravity is toward top."""
        return self.y < 1.0/2 or self.is_middle

    @property
    def is_bottom(self):
        """Return True if gravity is toward bottom."""
        return self.y > 1.0/2 or self.is_middle

    @property
    def is_left(self):
        """Return True if gravity is toward left."""
        return self.x < 1.0/2 or self.is_middle

    @property
    def is_right(self):
        """Return True if gravity is toward right."""
        return self.x > 1.0/2 or self.is_middle

    def invert(self, vertical=True, horizontal=True):
        """Invert the gravity (left becomes right, top becomes bottom)."""
        if vertical:
            y = 1.0 - self.y
        if horizontal:
            x = 1.0 - self.x
        return Gravity(x, y)

    def __eq__(self, other):
        return ((self.x, self.y) ==
                (other.x, other.y))

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return '(%.2f, %.2f)' % (self.x, self.y)


class Size(object):

    """Size encapsulates width and height of the object."""

    def __init__(self, width, height):
        self.width = width
        self.height = height

    def __eq__(self, other):
        return ((self.width, self.height) == (other.width, other.height))

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        string = 'width: %s, height: %s' 
        return string % (self.width, self.height)


class Position(object):

    """Position encapsulates Position of the object.

    Position coordinates starts at top-left corner of the desktop.

    """

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        return ((self.x, self.y) == (other.x, other.y))

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        string = 'x: %s, y: %s' 
        return string % (self.x, self.y)


class Geometry(Position, Size):

    """Geometry combines Size and Position of the object.

    Position coordinates (x, y) starts at top left corner of the desktop.
    (x2, y2) are the coordinates of the bottom-right corner of the object.

    """

    __DEFAULT_GRAVITY = Gravity(0, 0)

    #TODO: Maybe it will be better to keep gravity inside Geometry?
    def __init__(self, x, y, width, height,
                 gravity=__DEFAULT_GRAVITY):
        Size.__init__(self, int(width), int(height))
        x = int(x) - self.width * gravity.x
        y = int(y) - self.height * gravity.y
        Position.__init__(self, x, y)

    @property
    def x2(self):
        return self.x + self.width

    @property
    def y2(self):
        return self.y + self.height

    def set_position(self, x, y, gravity=__DEFAULT_GRAVITY):
        """Set position with (x,y) as gravity point."""
        self.x = x - self.width * gravity.x
        self.y = y - self.height * gravity.y

    def __eq__(self, other):
        return ((self.x, self.y, self.width, self.height) ==
                (other.x, other.y, other.width, other.height))

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        string = 'x: %s, y: %s, width: %s, height: %s, x2: %s, y2: %s' 
        return string % (self.x, self.y, 
                         self.width, self.height, 
                         self.x2, self.y2)


class Borders(object):

    """Borders encapsulate Window borders (frames/decorations)."""

    def __init__(self, left, right, top, bottom):
        self.top = top
        self.bottom = bottom
        self.left = left
        self.right = right

    @property
    def horizontal(self):
        """Return sum of left and right borders."""
        return self.left + self.right

    @property
    def vertical(self):
        """Return sum of top and bottom borders."""
        return self.top + self.bottom

    def __str__(self):
        string = 'left: %s, right: %s, top: %s, bottom %s' 
        return string % (self.left, self.right, self.top, self.bottom)


class EventDispatcher(threading.Thread):

    """Checks the event queue and dispatches events to correct handlers.

    EventDispatcher will run in separate thread.
    The self.__handlers attribute holds all registered EventHnadlers,
    it has structure as follows:
    self.__handlers = {win_id: {event_type: handler}} 
    That's why there can be only one handler per window/event_type.

    """

    def __init__(self, display):
        threading.Thread.__init__(self)
        self.__display = display
        self.__handlers = {}

    def run(self):
        """Perform event queue checking.

        Every 5ms check event queue for pending events and dispatch them.
        If there's no registered handlers stop running.

        """
        logging.info('Starting EventDispatcher')
        while self.__handlers:
            time.sleep(0.005)
            while self.__display.pending_events():
                # Dispatch all pending events if present
                self.__dispatch(self.__display.next_event())
        logging.info('Stopped EventDispatcher')

    def register(self, window, handler):
        """Register event handler and return new window's event mask."""
        logging.info('window=%s, handler.mask=%s, handler.types=%s' % 
                     (window.id, handler.mask, handler.types))
        if not window.id in self.__handlers:
            self.__handlers[window.id] = {}
        for type in handler.types:
            self.__handlers[window.id][type] = handler
        logging.debug('handlers %s' % self.__handlers)
        if not self.isAlive():
            self.start()
        return set([handler.mask 
                    for handler in self.__handlers[window.id].values()])

    def unregister(self, window, handler):
        """Unregister event handler and return new window's event mask.
        
        If handler is None all handlers will be unregistered.
        
        """
        if not handler and window.id in self.__handlers:
            logging.info('window=%s ALL handlers!' % (window.id))
            self.__handlers[window.id] = {}
        elif window.id in self.__handlers:
            logging.info('window=%s, handler.mask=%s, handler.types=%s' % 
                         (window.id, handler.mask, handler.types))
            for type in handler.types:
                if type in self.__handlers[window.id]:
                    del self.__handlers[window.id][type]
        if not self.__handlers[window.id]:
            del self.__handlers[window.id]
            logging.debug('handlers %s' % self.__handlers)
            return []
        logging.debug('handlers %s' % self.__handlers)
        return set([handler.mask 
                    for handler in self.__handlers[window.id].values()])

    def __dispatch(self, event):
        """Dispatch raw X event to correct handler."""
        if event.window.id not in self.__handlers:
            logging.error('No handler for window %s' % event.window.id)
            return
        win_handlers = self.__handlers[event.window.id]
        if not event.type in win_handlers:
            # Just skip unwanted events
            return
        win_handlers[event.type].handle_event(event)


class XObject(object):

    """Abstract base class for classes communicating with X Server.

    Encapsulates common methods for communication with X Server.

    """

    __DISPLAY = Display()
    __EVENT_DISPATCHER = EventDispatcher(__DISPLAY)

    # List of recognized key modifiers
    __KEY_MODIFIERS = {'Alt': X.Mod1Mask,
                       'Ctrl': X.ControlMask,
                       'Control': X.ControlMask,
                       'Shift': X.ShiftMask,
                       'Super': X.Mod4Mask,
                       'Win': X.Mod4Mask,}

    def __init__(self, win_id=None):
        self.__root = self.__DISPLAY.screen().root
        if win_id:
            # Normal window
            self._win = self.__DISPLAY.create_resource_object('window', win_id)
            self.id = win_id
        else:
            # WindowManager, act as root window
            self._win = self.__root 
            self.id = self._win.id

    @classmethod
    def atom(cls, name):
        """Return atom with given name."""
        return cls.__DISPLAY.intern_atom(name)

    def get_property(self, name):
        """Return property (None if there's no such property)."""
        atom = self.atom(name)
        property = self._win.get_full_property(atom, 0)
        return property

    def send_event(self, data, type, mask):
        """Send event from (to?) the root window."""
        event = protocol.event.ClientMessage(
                    window=self._win,
                    client_type=type,
                    data=(32, (data)))
        self.__root.send_event(event, event_mask=mask)

    def listen(self, event_handler):
        """Register new event handler and update event mask."""
        masks = self.__EVENT_DISPATCHER.register(self, event_handler)
        self.__set_event_mask(masks)

    def unlisten(self, event_handler=None):
        """Unregister event handler(s) and update event mask.
        
        If event_handler is None all handlers will be unregistered.

        """
        masks = self.__EVENT_DISPATCHER.unregister(self, event_handler)
        self.__set_event_mask(masks)

    def __set_event_mask(self, masks):
        """Update event mask."""
        event_mask = 0
        logging.debug(masks)
        for mask in masks:
            event_mask = event_mask | mask
        self._win.change_attributes(event_mask=event_mask)

    #TODO: Make NumLock an option?
    def grab_key(self, modifiers, keycode, numlock):
        """Grab key.

        Grab key alone, with CapsLock on and/or with NumLock on.

        """
        if numlock in [0, 2]:
            self._win.grab_key(keycode, modifiers, 
                               1, X.GrabModeAsync, X.GrabModeAsync)
            self._win.grab_key(keycode, modifiers | X.LockMask, 
                               1, X.GrabModeAsync, X.GrabModeAsync)
        if numlock in [1, 2]:
            self._win.grab_key(keycode, modifiers | X.Mod2Mask, 
                               1, X.GrabModeAsync, X.GrabModeAsync)
            self._win.grab_key(keycode, modifiers | X.LockMask | X.Mod2Mask, 
                               1, X.GrabModeAsync, X.GrabModeAsync)

    def ungrab_key(self, modifiers, keycode, numlock):
        """Ungrab key.

        Ungrab key alone, with CapsLock on and/or with NumLock on.

        """
        if numlock in [0, 2]:
            self._win.ungrab_key(keycode, modifiers)
            self._win.ungrab_key(keycode, modifiers | X.LockMask)
        if numlock in [1, 2]:
            self._win.ungrab_key(keycode, modifiers | X.Mod2Mask)
            self._win.ungrab_key(keycode, modifiers | X.LockMask | X.Mod2Mask)

    def _translate_coords(self, x, y):
        """Return translated coordinates.
        
        Untranslated coordinates are relative to window.
        Translated coordinates are relative to desktop.

        """
        return self._win.translate_coords(self.__root, x, y)

    @classmethod
    def keycode(cls, code, key=''):
        """Convert key as string(s) into (modifiers, keycode) pair.
        
        There must be both modifier(s) and key persenti. If you send both
        modifier(s) and key in one string, they must be separated using '-'. 
        Modifiers must be separated using '-'.
        Keys are case insensitive.
        If you want to use upper case use Shift modifier.
        Only modifiers defined in __KEY_MODIFIERS are valid.
        For example: "Ctrl-A", "Super-Alt-x"
        
        """
        code = code.split('-')
        if not key:
            key = code[-1]
            masks = code[:-1]
        else:
            masks = code
        
        # TODO: Check this part... not sure why it looks like that...
        modifiers = 0
        if masks[0]:
            for mask in masks:
                if not mask in cls.__KEY_MODIFIERS.keys():
                    continue
                modifiers = modifiers | cls.__KEY_MODIFIERS[mask]
        else:
            modifiers = X.AnyModifier
        
        keysym = XK.string_to_keysym(key)
        keycode = cls.__DISPLAY.keysym_to_keycode(keysym)
        return (modifiers, keycode)

    @classmethod
    def flush(cls):
        """Flush request queue to X Server."""
        cls.__DISPLAY.flush()

    @classmethod
    def sync(cls):
        """Flush request queue to X Server, wait until server processes them."""
        cls.__DISPLAY.sync()


class Window(XObject):

    """Window object (X Server client?)."""

    # List of window managers that don't need position translation
    __DONT_TRANSLATE = ['compiz']
    __ADJUST_GEOMETRY = ['compiz', 'kwin', 'e16', 
                         'icewm', 'blackbox', 'fvwm',]
                         #'fluxbox',]

    # List of window types
    TYPE_DESKTOP = XObject.atom('_NET_WM_WINDOW_TYPE_DESKTOP')
    TYPE_DOCK = XObject.atom('_NET_WM_WINDOW_TYPE_DOCK')
    TYPE_TOOLBAR = XObject.atom('_NET_WM_WINDOW_TYPE_TOOLBAR')
    TYPE_MENU = XObject.atom('_NET_WM_WINDOW_TYPE_MENU')
    TYPE_UTILITY = XObject.atom('_NET_WM_WINDOW_TYPE_UTILITY')
    TYPE_SPLASH = XObject.atom('_NET_WM_WINDOW_TYPE_SPLASH')
    TYPE_DIALOG = XObject.atom('_NET_WM_WINDOW_TYPE_DIALOG')
    TYPE_NORMAL = XObject.atom('_NET_WM_WINDOW_TYPE_NORMAL')

    # List of window states
    STATE_MODAL = XObject.atom('_NET_WM_STATE_MODAL')
    STATE_STICKY = XObject.atom('_NET_WM_STATE_STICKY')
    STATE_MAXIMIZED_VERT = XObject.atom('_NET_WM_STATE_MAXIMIZED_VERT')
    STATE_MAXIMIZED_HORZ = XObject.atom('_NET_WM_STATE_MAXIMIZED_HORZ')
    STATE_SHADED = XObject.atom('_NET_WM_STATE_SHADED')
    STATE_SKIP_TASKBAR = XObject.atom('_NET_WM_STATE_SKIP_TASKBAR')
    STATE_SKIP_PAGER = XObject.atom('_NET_WM_STATE_SKIP_PAGER')
    STATE_HIDDEN = XObject.atom('_NET_WM_STATE_HIDDEN')
    STATE_FULLSCREEN = XObject.atom('_NET_WM_STATE_FULLSCREEN')
    STATE_ABOVE = XObject.atom('_NET_WM_STATE_ABOVE')
    STATE_BELOW = XObject.atom('_NET_WM_STATE_BELOW')
    STATE_DEMANDS_ATTENTION = XObject.atom('_NET_WM_STATE_DEMANDS_ATTENTION')

    # Mode values (for maximize and shade functions)
    MODE_UNSET = 0
    MODE_SET = 1
    MODE_TOGGLE = 2

    def __init__(self, win_id):
        XObject.__init__(self, win_id)
        self.__translate_coords, self.__adjust_geometry = self.__check()

    def __check(self):
        """Check if position should be translated or adjusted."""
        name = WindowManager().name.lower()
        translate_coords = name not in Window.__DONT_TRANSLATE
        adjust_geometry = name in Window.__ADJUST_GEOMETRY
        return (translate_coords, adjust_geometry)

    @property
    def type(self):
        """Return list of window's type(s)."""
        type = self.get_property('_NET_WM_WINDOW_TYPE')
        if not type:
            return [Window.TYPE_NORMAL]
        return type.value

    @property
    def state(self):
        """Return list of window's state(s)."""
        state = self.get_property('_NET_WM_STATE')
        if not state:
            return []
        return state.value

    @property
    def parent_id(self):
        """Return window's parent id."""
        parent = self._win.get_wm_transient_for()
        if parent:
            return parent.id
        else:
            return None


    @property
    def parent(self):
        """Return window's parent."""
        parent_id = self.parent_id
        if parent_id:
            return Window(parent_id)
        else:
            return None

    @property
    def name(self):
        """Return window's name."""
        name = self.get_property('_NET_WM_NAME')
        if not name:
            name = self._win.get_full_property(Xatom.WM_NAME, 0)
            if not name:        
                return ''
        return name.value

    @property
    def class_name(self):
        """Return window's class name."""
        class_name = self._win.get_wm_class()
        return class_name

    @property
    def desktop(self):
        """Return desktop number the window is in."""
        desktop = self.get_property('_NET_WM_DESKTOP')
        if not desktop:
            return 0
        # FIXME: Metacity return 0xFFFFFFFF when "show on all desktops"
        return desktop.value[0]

    def __borders(self):
        """Return raw borders info."""
        extents = self.get_property('_NET_FRAME_EXTENTS')
        if not extents:
            return (0, 0, 0, 0)
        return extents.value

    @property
    def borders(self):
        """Return window's borders (frames/decorations)."""
        borders = self.__borders()
        return Borders(*borders)

    def __geometry(self):
        """Return raw geometry info (translated if needed)."""
        geometry = self._win.get_geometry()
        if self.__translate_coords:
            # if neeeded translate coords and multiply them by -1
            translated = self._translate_coords(geometry.x, geometry.y)
            return (-translated.x, -translated.y, 
                    geometry.width, geometry.height)
        return (geometry.x, geometry.y, 
                geometry.width, geometry.height)

    @property
    def geometry(self):
        """Return window's geometry.

        (x, y) coordinates are the top-left corner of the window,
        relative to the left-top corner of desktop.
        Position and size *includes* window's borders!
        Position is translated if needed.

        """
        x, y, width, height = self.__geometry()
        left, right, top, bottom = self.__borders()
        if self.__adjust_geometry:
            x -= left
            y -= top
        return Geometry(x, y,
                        width + left + right,
                        height + top + bottom)

    def move_resize(self, geometry, on_resize=Gravity(0, 0)):
        """Move or resize window using provided geometry.

        Postion and size must include window's borders. 

        """
        left, right, top, bottom = self.__borders()
        x = geometry.x
        y = geometry.y
        width = geometry.width - (left + right)
        height = geometry.height - (top + bottom)
        geometry_size = (width, height)
        current = self.__geometry()
        hints = self._win.get_wm_normal_hints()
        # This is a fix for WINE, OpenOffice and KeePassX windows
        if hints and hints.win_gravity == X.StaticGravity:
            x += left
            y += top
        # Reduce size to maximal allowed value
        if hints and hints.max_width: 
            width = min([width, hints.max_width])
        if hints and hints.max_height:
            height = min([height, hints.max_height])
        # Don't try to set size lower then minimal
        if hints and hints.min_width: 
            width = max([width, hints.min_width])
        if hints and hints.min_height:
            height = max([height, hints.min_height])
        # Set correct size if it is incremental, take base in account
        if hints and hints.width_inc: 
            if hints.base_width:
                base = hints.base_width
            else:
                base = current[2] % hints.width_inc
            width = ((width - base) / hints.width_inc) * hints.width_inc
            width += base
            if hints.min_width and width < hints.min_width:
                width += hints.width_inc
        if hints and hints.height_inc:
            if hints.base_height:
                base = hints.base_height
            else:
                base = current[3] % hints.height_inc
            height = ((height - base) / hints.height_inc) * hints.height_inc
            height += base
            if hints.height_inc and height < hints.min_height:
                height += hints.height_inc
        # Adjust position after size change
        if (width, height) != geometry_size:
            x = x + (geometry_size[0] - width) * on_resize.x
            y = y + (geometry_size[1] - height) * on_resize.y
        self._win.configure(x=x, y=y, width=width, height=height)

    def maximize(self, mode):
        """Maximize window (both vertically and horizontally)."""
        #TODO: separate VERT and HORZ?
        data = [mode, 
                Window.STATE_MAXIMIZED_VERT,
                Window.STATE_MAXIMIZED_HORZ,
                0, 0]
        self.__change_state(data)

    def shade(self, mode):
        """Shade window (if supported by window manager)."""
        data = [mode, 
                Window.STATE_SHADED,
                0, 0, 0]
        self.__change_state(data)

    def reset(self):
        """Unmaximize (both horizontally and vertically) and unshade."""
        #TODO: What about Fullscreen?
        self.maximize(self.MODE_UNSET)
        self.shade(self.MODE_UNSET)

    def __change_state(self, data):
        """Send _NET_WM_STATE event to the root window."""
        type = self.atom('_NET_WM_STATE')
        mask = X.SubstructureRedirectMask
        self.send_event(data, type, mask)

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return not self.id == other.id

    def full_info(self):
        """Print full window's info, for debug use only."""
        print '----------==========----------'
        print 'ID:', self.id
        print 'NAME:', self.name
        print 'CLASS:', self.class_name
        print 'TYPE:', self.type
        print 'STATE:', self.state
        print 'DESKTOP:', self.desktop
        print 'BORDERS:', self.borders
        print 'BORDERS_raw:', self.__borders()
        print 'GEOMETRY:', self.geometry
        print 'GEOMETRY_raw:', self._win.get_geometry()
        print 'PARENT:', self.parent_id, self.parent
        print 'NORMAL_HINTS:', self._win.get_wm_normal_hints()
        print 'ATTRIBUTES:', self._win.get_attributes()
        print 'QUERY_TREE:', self._win.query_tree()
        print '----------==========----------'


class WindowManager(XObject):
    
    """Window Manager (or root window in X programming terms).
    
    WindowManger's self._win refers to the root window.
    It is Singleton.

    """

    # Instance of the WindowManger class, make it Singleton.
    __INSTANCE = None

    def __new__(cls):
        if cls.__INSTANCE:
            return cls.__INSTANCE
        else:
            manager = object.__new__(cls)
            XObject.__init__(manager)
            cls.__INSTANCE = manager
            return manager

    @property
    def name(self):
        """Return window manager's name.

        '' is returned if window manager doesn't support EWMH.

        """
        win_id = self.get_property('_NET_SUPPORTING_WM_CHECK')
        if not win_id:
            return ''
        win = XObject(win_id.value[0])
        name = win.get_property('_NET_WM_NAME')
        if name:
            return name.value
        else:
            return ''

    @property
    def desktops(self):
        """Return number of desktops."""
        number = self.get_property('_NET_NUMBER_OF_DESKTOPS')
        if not number:
            return 1
        return number.value[0]

    @property
    def desktop(self):
        """Return current desktop number."""
        desktop = self.get_property('_NET_CURRENT_DESKTOP')
        return desktop.value[0]

    @property
    def desktop_size(self):
        """Return size of current desktop."""
        geometry = self.get_property('_NET_DESKTOP_GEOMETRY').value
        return Size(geometry[0], geometry[1])

    @property
    def workarea_geometry(self):
        """Return geometry of current workarea (desktop without panels)."""
        workarea = self.get_property('_NET_WORKAREA').value
        return Geometry(workarea[0], workarea[1], 
                        workarea[2], workarea[3])

    @property
    def viewport(self):
        """Return position of current viewport. 

        If desktop is large it might be divided into several viewports.

        """
        viewport = self.get_property('_NET_DESKTOP_VIEWPORT').value
        return Position(viewport[0], viewport[1])

    def active_window_id(self):
        """Return only id of active window."""
        win_id = self.get_property('_NET_ACTIVE_WINDOW').value[0]
        return win_id

    def active_window(self):
        """Return active window."""
        window_id = self.active_window_id()
        return Window(window_id)

    def windows_ids(self):
        """Return list of all windows' ids (with bottom-top stacking order)."""
        windows_ids = self.get_property('_NET_CLIENT_LIST_STACKING').value
        return windows_ids

    def windows(self, filter_method=None):
        """Return list of all windows (with bottom-top stacking order)."""
        windows_ids = self.windows_ids()
        windows = [Window(win_id) for win_id in windows_ids]
        return [window for window in windows if filter_method(window)]

