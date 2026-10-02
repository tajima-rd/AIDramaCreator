# core/gis/feature.py
"""地物の型。"""

from typing import Any, Optional

# 地物: (形(WKT。無ければNone), 属性)
Feature = tuple[Optional[str], dict[str, Any]]
