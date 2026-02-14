"""
Pine Indicator Module
"""
from typing import Dict, Any, Optional

class PineIndicator:
    """
    Class representing a Pine Script indicator.
    """
    def __init__(self, options: Dict[str, Any]):
        """
        Initialize Pine indicator.

        Args:
            options: Indicator options
        """
        self._options = options
        self._type = 'Script@tv-scripting-101!'

    @property
    def pine_id(self) -> str:
        """Get indicator ID"""
        return self._options.get('pineId', '')

    @property
    def pine_version(self) -> str:
        """Get indicator version"""
        return self._options.get('pineVersion', '')

    @property
    def description(self) -> str:
        """Get indicator description"""
        return self._options.get('description', '')

    @property
    def short_description(self) -> str:
        """Get indicator short description"""
        return self._options.get('shortDescription', '')

    @property
    def inputs(self) -> Dict[str, Any]:
        """Get indicator inputs"""
        return self._options.get('inputs', {})

    @property
    def plots(self) -> Dict[str, str]:
        """Get indicator plots"""
        return self._options.get('plots', {})

    @property
    def type(self) -> str:
        """Get indicator type"""
        return self._type

    def set_type(self, type: str = 'Script@tv-scripting-101!') -> None:
        """
        Set indicator type.

        Args:
            type: Indicator type string
        """
        self._type = type

    @property
    def script(self) -> str:
        """Get indicator source script"""
        return self._options.get('script', '')

    def set_option(self, key: str, value: Any) -> None:
        """
        Set an indicator input option.

        Args:
            key: Option key
            value: Option value
        """
        prop_id = ''

        # Look for input parameters
        if f'in_{key}' in self._options['inputs']:
            prop_id = f'in_{key}'
        elif key in self._options['inputs']:
            prop_id = key
        else:
            # Search by inline or internalID
            for input_id, input_data in self._options['inputs'].items():
                if input_data.get('inline') == key or input_data.get('internalID') == key:
                    prop_id = input_id
                    break

        if prop_id and prop_id in self._options['inputs']:
            input_data = self._options['inputs'][prop_id]

            # Type validation
            types_map = {
                'bool': bool,
                'integer': int,
                'float': float,
                'text': str
            }

            if input_data['type'] in types_map:
                if not isinstance(value, types_map[input_data['type']]):
                    raise TypeError(f"Input '{input_data['name']}' ({prop_id}) must be a {types_map[input_data['type']].__name__}!")

            # Options value validation
            if 'options' in input_data and value not in input_data['options']:
                raise ValueError(f"Input '{input_data['name']}' ({prop_id}) must be one of these values: {input_data['options']}")

            input_data['value'] = value
        else:
            raise KeyError(f"Input '{key}' not found ({prop_id}).")
