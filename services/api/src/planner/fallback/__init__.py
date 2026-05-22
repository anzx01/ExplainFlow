# Import all scene_builder modules to register their methods on FallbackSceneBuilder via monkey-patching.
# Order matters: base must be first, then draw (which adds add_text/add_stroke), then all build_* methods.
from .scene_builder_base import FallbackSceneBuilder  # noqa: F401
from . import scene_builder_draw  # noqa: F401
from . import scene_builder_annotation  # noqa: F401
from . import scene_builder_habits  # noqa: F401
from . import scene_builder_railway  # noqa: F401
from . import scene_builder_raster  # noqa: F401
from . import scene_builder_reference  # noqa: F401
from . import scene_builder_diagrams  # noqa: F401
from . import scene_builder_diagrams2  # noqa: F401
from . import scene_builder_board  # noqa: F401
from . import scene_builder_device  # noqa: F401
from . import scene_builder_main  # noqa: F401
