import dash
from dash.development.base_component import Component, _explicitize_args


class HmdlFlow(Component):
    _children_props = []
    _base_nodes = ['children']
    _namespace = 'dash_hmdl_flow'
    _type = 'HmdlFlow'

    @_explicitize_args
    def __init__(
        self,
        id=Component.UNDEFINED,
        topologyData=Component.UNDEFINED,
        hubDc=Component.UNDEFINED,
        height=Component.UNDEFINED,
        clickedNode=Component.UNDEFINED,
        **kwargs,
    ):
        self._prop_names = ['id', 'topologyData', 'hubDc', 'height', 'clickedNode']
        self._valid_wildcard_attributes = []
        self.available_properties = self._prop_names
        self.available_wildcard_properties = []
        _explicit_args = kwargs.pop('_explicit_args')
        _locals = locals()
        _locals.update(kwargs)
        args = {k: _locals[k] for k in _explicit_args}
        super(HmdlFlow, self).__init__(**args)
