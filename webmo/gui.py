#handle abstract base class
from abc import ABC, abstractmethod

class _WebMOGUIBase(ABC):
	"""The _WebMOGUIBase class is an abstract base class for all Python-based GUIs for WebMO.
    """

	def __init__(self, template, query_vars, additional_vars):
		self._query_vars = query_vars
		self._additional_vars = additional_vars

	@abstractmethod	
	def display(self):
		pass

	@abstractmethod	
	def get_variables(self):
		pass

class JupyterGUI(_WebMOGUIBase):
	"""The JupyterGUI class is a menu-driven Jupyter GUI interface for setting up WebMO jobs.
	
	The class utilizes IPython widgets to present a menu-driven interface, using a subset
	of user-specified list of template variables.
    """
	import ipywidgets
		
	def __init__(self, template, query_vars, additional_vars=None):
		"""Constructor for JupyterGUI
        
        This constructor generates a JupyterGUI object.
        
        Args:
            template(dict): A specific template, selected from WebMOREST.get_templates()
            query_vars(list): A subset of variables to use when generating the GUI
            additional_vars(dict, optional): A dictionary of additional variables/values to utilize during input file generation
            
        Returns:
            object: The newly constructed JupyterGUI object
    	"""

		_WebMOGUIBase.__init__(self, template, query_vars, additional_vars)
		self._widgets = []

		for var in query_vars:

			if	template['variables'][var]['type'] == 'checkbox':
				#handle checkbox options
				self._widgets.append(
					self.ipywidgets.widgets.Checkbox(
						value=True if template['variables'][var]['default'] == 'on' else False,
    					description=var,
						disabled=False));
			elif template['variables'][var]['type'] == 'dropdown':
				#handle select/dropdown options
				self._widgets.append(
					self.ipywidgets.widgets.Dropdown(
						options=template['variables'][var]['options'],
						value=template['variables'][var]['default'],
    					description=var,
						disabled=False));
			else:
				#handle text input
				self._widgets.append(
					self.ipywidgets.widgets.Text(
					    description=var,
					    value=template['variables'][var]['default'],
					    disabled=False));    

	def display(self):
		"""Presents the menu-driven JupyterGUI
        
        Displays the JupyterGUI using a system of IPython widgets.
        
        Args:
            None
            
        Returns:
            None
    	"""
		for widget in self._widgets:
			display(widget)

	def get_variables(self):
		"""Returns a populated variables dictionary.
        
        Returns a populated variables dictionary, generated using the user-selected
        menu options, along with an additional user-specified key/value pairs (additional_vars)
        
        Args:
            None
            
        Returns:
            A populated dictionary of of variables and values.
    	"""

		#add in additional user-specified variables
		variables = {**self._additional_vars}

		for (var, widget) in zip(self._query_vars, self._widgets):
			if isinstance(widget, self.ipywidgets.Checkbox):
				variables[var] = "on" if widget.value == True else ""
			else:
				variables[var] = widget.value
			
		return variables
