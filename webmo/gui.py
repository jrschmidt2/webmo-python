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
        """Presents the menu-driven JupyterGUI

        Displays the JupyterGUI using a system of IPython widgets.

        Args:
            None

        Returns:
            None
        """
        pass

    @abstractmethod
    def get_variables(self):
        """Returns a populated variables dictionary.

        Returns a populated variables dictionary, generated using the user-selected
        menu options, along with an additional user-specified key/value pairs (additional_vars)

        Args:
            None

        Returns:
            A populated dictionary of of variables and values.
        """
        pass

class JupyterGUI(_WebMOGUIBase):
    """The JupyterGUI class is a menu-driven Jupyter GUI interface for setting up WebMO jobs.

    The class utilizes IPython widgets to present a menu-driven interface, using a subset
    of user-specified list of template variables.
    """
    try:
        import ipywidgets
    except:
        #fail silently, since this should never happen in Jupyter
        pass #print('ipywidgets not found; disabling support for JupyterGUI')

    import time

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
        self._display_time = -1

        for var in query_vars:
            if template['variables'][var]['type'] == 'checkbox':
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

        self._display_time = self.time.time()

        for widget in self._widgets:
            display(widget)

    def get_variables(self):

        MIN_INPUT_TIME = 1.0
        # sanity check to make sure user has had time to input something
        # fail this call during re-execution of entire notebook at once
        elapsed_time = self.time.time() - self._display_time
        if self._display_time == -1 or elapsed_time < MIN_INPUT_TIME:
            raise RuntimeError('Must provide JupyterGUI input before calling get_variables')

        # add in additional user-specified variables
        if (self._additional_vars != None):
            variables = {**self._additional_vars}
        else:
            variables = {}

        for (var, widget) in zip(self._query_vars, self._widgets):
            if isinstance(widget, self.ipywidgets.Checkbox):
                variables[var] = "on" if widget.value == True else ""
            else:
                variables[var] = widget.value

        return variables

class ConsoleGUI(_WebMOGUIBase):
    """The ConsoleGUI class is a text-based interface for setting up WebMO jobs.

    The class utilizes the questionary library to present a neat interface using a subset
    of user-specified list of template variables.
    """

    def __init__(self, template, query_vars, additional_vars=None):
        """Constructor for ConsoleGUI

        This constructor generates a ConsoleGUI object.

        Args:
            template(dict): A specific template, selected from WebMOREST.get_templates()
            query_vars(list): A subset of variables to use when generating the GUI
            additional_vars(dict, optional): A dictionary of additional variables/values to utilize during input file generation

        Returns:
            object: The newly constructed ConsoleGUI object
        """

        import questionary as q

        _WebMOGUIBase.__init__(self, template, query_vars, additional_vars)
        self._questions = []
        for var in query_vars:
            # checkbox options
            if template['variables'][var]['type'] == 'checkbox':
                self._questions.append(q.confirm(var));
            # select/dropdown options
            elif template['variables'][var]['type'] == 'dropdown':
                choices = []
                for key, value in template['variables'][var]['options'].items():
                    choices.append(q.Choice(title=key, value=value))

                self._questions.append(
                    q.select(
                        var,
                        choices=choices,
                        use_shortcuts=True));
            # text input
            else:
                self._questions.append(
                    q.text(var));


    def display(self):

        self._answers = []
        for question in self._questions:
            self._answers.append(question.ask())

    def get_variables(self):

        # add in additional user-specified variables
        if (self._additional_vars != None):
            variables = {**self._additional_vars}
        else:
            variables = {}

        for (var, value) in zip(self._query_vars, self._answers):
            if isinstance(value, bool):
                variables[var] = "on" if value else ""
            else:
                variables[var] = value

        return variables
