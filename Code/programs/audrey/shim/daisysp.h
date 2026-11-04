// Shim: instead of DaisySP's umbrella header (all of DaisySP), only the parts
// the AudreyTouch engine uses. The vendored files include <daisysp.h>
// unchanged; this directory comes first in the include path.
#pragma once
#include "Utility/dsp.h"
#include "Utility/delayline.h"
#include "Noise/whitenoise.h"
#include "Synthesis/oscillator.h"
#include "Effects/overdrive.h"
#include "Dynamics/crossfade.h"
#include "Dynamics/limiter.h"
#include "Filters/tone.h"        // DaisySP-LGPL
#include "Effects/reverbsc.h"    // DaisySP-LGPL
