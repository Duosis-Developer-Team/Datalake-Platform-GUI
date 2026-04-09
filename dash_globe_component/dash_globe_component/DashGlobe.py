import dash
from dash.development.base_component import Component, _explicitize_args


class DashGlobe(Component):
    _children_props = []
    _base_nodes = ['children']
    _namespace = 'dash_globe_component'
    _type = 'DashGlobe'

    @_explicitize_args
    def __init__(self, id=Component.UNDEFINED, pointsData=Component.UNDEFINED,
                 focusRegion=Component.UNDEFINED, clickedPoint=Component.UNDEFINED,
                 globeImageUrl=Component.UNDEFINED, width=Component.UNDEFINED,
                 height=Component.UNDEFINED, **kwargs):
        self._prop_names = ['id', 'pointsData', 'focusRegion', 'clickedPoint',
                            'globeImageUrl', 'width', 'height']
        self._valid_wildcard_attributes = []
        self.available_properties = self._prop_names
        self.available_wildcard_properties = []
        _explicit_args = kwargs.pop('_explicit_args')
        _locals = locals()
        _locals.update(kwargs)
        args = {k: _locals[k] for k in _explicit_args}
        super(DashGlobe, self).__init__(**args)
