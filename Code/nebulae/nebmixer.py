# nebmixer.py
import ctypes
import os

LEFT = 0
RIGHT = 1
_libasound = None
_mixer = None
_capturecontrol_handle = None
_hifi_output_handle = None
_enable = True

def _log_message(message):
    print("NebMixer Message: " + message + "\n")

def _log_error(message):
    print("NebMixer Error: " + message + "\n")

def _log_warning(message):
    print("NebMixer Warning: " + message + "\n")

def _loadlid():
    global _libasound
    if _libasound is None:
        _log_message("_init_lib_once")
        try:
            _libasound = ctypes.CDLL("libasound.so")

            _libasound.snd_mixer_open.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
            _libasound.snd_mixer_open.restype = ctypes.c_int

            _libasound.snd_mixer_attach.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            _libasound.snd_mixer_attach.restype = ctypes.c_int

            _libasound.snd_mixer_detach.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            _libasound.snd_mixer_detach.restype = ctypes.c_int

            _libasound.snd_mixer_selem_register.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            _libasound.snd_mixer_selem_register.restype = ctypes.c_int

            _libasound.snd_mixer_load.argtypes = [ctypes.c_void_p]
            _libasound.snd_mixer_load.restype = ctypes.c_int

            _libasound.snd_mixer_close.argtypes = [ctypes.c_void_p]
            _libasound.snd_mixer_close.restype = ctypes.c_int

            _libasound.snd_mixer_find_selem.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            _libasound.snd_mixer_find_selem.restype = ctypes.c_void_p

            _libasound.snd_mixer_selem_set_capture_volume.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_long
            ]
            _libasound.snd_mixer_selem_set_capture_volume.restype = ctypes.c_int

            _libasound.snd_mixer_selem_set_playback_switch.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_int
            ]
            _libasound.snd_mixer_selem_set_playback_switch.restype = ctypes.c_int

            # ---- ADDED: correct selem-id + joined switch support ----
            _libasound.snd_mixer_selem_id_malloc.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
            _libasound.snd_mixer_selem_id_malloc.restype = ctypes.c_int

            _libasound.snd_mixer_selem_id_set_name.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            _libasound.snd_mixer_selem_id_set_index.argtypes = [ctypes.c_void_p, ctypes.c_uint]

            _libasound.snd_mixer_selem_set_playback_switch_all.argtypes = [
                ctypes.c_void_p, ctypes.c_int
            ]
            _libasound.snd_mixer_selem_set_playback_switch_all.restype = ctypes.c_int
            # --------------------------------------------------------

            _log_message("_init_lib_once end")
        except OSError:
            _log_error("_init_lib_once - OSError")
            return False
    return True

def init(device=b"hw:sndrpiproto",
         capturecontrol=b"Capture",
         hifi_control_name=b"Output Mixer HiFi"):
    global _mixer, _capturecontrol_handle, _hifi_output_handle

    _log_message("initMixer")
    if _mixer is not None:
        return True

    if not _loadlid():
        return False

    _mixer = ctypes.c_void_p()

    device_c = ctypes.c_char_p(device)

    if _libasound.snd_mixer_open(ctypes.byref(_mixer), 0) < 0:
        _log_error("Cannot open ALSA mixer")
        _mixer = None
        return False

    if _libasound.snd_mixer_attach(_mixer, device_c) < 0:
        _log_error("Cannot attach mixer to device")
        _libasound.snd_mixer_close(_mixer)
        _mixer = None
        return False

    if _libasound.snd_mixer_selem_register(_mixer, None, None) < 0:
        _log_error("Cannot register mixer element")
        remove()
        return False

    if _libasound.snd_mixer_load(_mixer) < 0:
        _log_error("Cannot load mixer elements")
        remove()
        return False

    strcap = ctypes.create_string_buffer(capturecontrol)
    _capturecontrol_handle = _libasound.snd_mixer_find_selem(_mixer, strcap)
    if not _capturecontrol_handle:
        _log_error("Capture control not found")
        remove()
        return False

    # ---- FIXED: proper lookup of 'Output Mixer HiFi',0 ----
    sid = ctypes.c_void_p()
    _libasound.snd_mixer_selem_id_malloc(ctypes.byref(sid))
    _libasound.snd_mixer_selem_id_set_name(sid, hifi_control_name)
    _libasound.snd_mixer_selem_id_set_index(sid, 0)

    _hifi_output_handle = _libasound.snd_mixer_find_selem(_mixer, sid)
    if not _hifi_output_handle:
        _log_warning("HiFi Output control not found")
    # ------------------------------------------------------

    return True

def remove(device=b"hw:sndrpiproto"):
    global _mixer, _capturecontrol_handle, _hifi_output_handle

    if _mixer is None:
        return True

    device_c = ctypes.c_char_p(device)
    _libasound.snd_mixer_detach(_mixer, device_c)
    _libasound.snd_mixer_close(_mixer)

    _capturecontrol_handle = None
    _hifi_output_handle = None
    _mixer = None
    return True

def enable():
    global _enable
    _enable = True

    if _libasound is None or _hifi_output_handle is None:
        return

    _libasound.snd_mixer_selem_set_playback_switch_all(
        _hifi_output_handle, 1
    )

def disable():
    global _enable
    _enable = False

    if _libasound is None or _hifi_output_handle is None:
        return

    _libasound.snd_mixer_selem_set_playback_switch_all(
        _hifi_output_handle, 0
    )

def inputLevel(volume):
    global _capturecontrol_handle, _enable

    if not _enable:
        return

    if not init():
        return

    if _capturecontrol_handle is None:
        return

    volume = max(0, min(31, int(volume)))
    ctvol = ctypes.c_long(volume)

    _libasound.snd_mixer_selem_set_capture_volume(
        _capturecontrol_handle, LEFT, ctvol
    )
    _libasound.snd_mixer_selem_set_capture_volume(
        _capturecontrol_handle, RIGHT, ctvol
    )
