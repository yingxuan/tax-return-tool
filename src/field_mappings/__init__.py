"""Field mappings for IRS/FTB fillable PDF forms.

Each module provides a mapper function: TaxReturn -> dict[str, str]
that maps PDF AcroForm field names to formatted values.
"""

from typing import Callable, Dict, Tuple

from ..models import TaxReturn

# Type alias for mapper functions
MapperFn = Callable[[TaxReturn], Dict[str, str]]

# Registry: form_name -> (mapper_function, template_filename)
# Template filename is relative to pdf_templates/<year>/
_REGISTRY: Dict[str, Tuple[MapperFn, str]] = {}


def register(form_name: str, template_file: str):
    """Decorator to register a form mapper."""
    def decorator(fn: MapperFn) -> MapperFn:
        _REGISTRY[form_name] = (fn, template_file)
        return fn
    return decorator


def get_mapper(form_name: str) -> Tuple[MapperFn, str]:
    """Get mapper function and template filename for a form."""
    if form_name not in _REGISTRY:
        raise ValueError(f"Unknown form: {form_name}. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[form_name]


def available_forms() -> list:
    """Return list of registered form names."""
    return list(_REGISTRY.keys())


# Import all mapper modules to trigger registration
from . import f1040  # noqa: E402, F401
from . import schedule_a  # noqa: E402, F401
from . import schedule_b  # noqa: E402, F401
from . import schedule_e  # noqa: E402, F401
from . import ca540  # noqa: E402, F401
