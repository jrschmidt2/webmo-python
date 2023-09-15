import requests
import json
import time
from getpass import getpass

try:
    from IPython.display import display, Javascript
    has_ipython = True
except ImportError:
    has_ipython = False

class WebMOREST:
    """The WebMOREST class provides an object-oriented Python API for the WebMO REST interface.
    
    The WebMOREST class provides a simple Python API to access the WebMO REST interface. As of now
    there are no public methods. Session tokens are handled automatically handled during object
    creation/destruction.
    """
    
    def __init__(self, base_url, username, password=""):
        """Constructor for WebMOREST
        
        This constructor generates a WebMOREST object and also generates and stores a newly
        session token.
        
        Args:
            base_url(str): The base URL (ending in rest.cgi) of the WeBMO rest endpoint
            username(str): The WebMO username
            password(str, optional): The WebMO password; if omitted, this is supplied interactively
            
        Returns:
            object: The newly constructed WebMO object
        """
        
        #prompt for WebMO password if not specified
        if not password:
            password=getpass(prompt="Enter WebMO password for user %s:" % username)
        #obtain a REST token using the specified credentials
        login={'username' : username, 'password' : password} #WebMO login information, used to retrieve a REST access token
        r = requests.post(base_url + '/sessions', data=login)
        r.raise_for_status() #raise an exception if there is a problem with the request
        
        self._base_url = base_url
        self._auth=r.json() #save an authorization token need to authenticate future REST requests
        
        self._init_javascript = True
        if has_ipython:
            self._inject_javascript()

        
    def __del__(self):
        """Destructor for WebMOREST
        
        This destructor automatically deletes the session token using the REST interface
        """
        
        #End the REST sessions
        r = requests.delete(self._base_url + '/sessions', params=self._auth)
        #do not raise an exception for a failed request in this case due to issues
        #with object management in Jupyter (i.e. on code re-run, a new token is made
        #prior to deletion!)
    
    #
    # Users resource
    # 
    def get_users(self):
        """Fetches a list of available WebMO users
        
        This call returns a list of available WebMO users. For non-administrative users, this will be
        only the current authenticated user. For group administrators, this call will return all users
        in the group. For system administrators, this call will return all system users.
        
        Returns:
            A list of users
        """
        
        r = requests.get(self._base_url + "/users", params=self._auth)
        r.raise_for_status()
        return r.json()["users"]
        
    def get_user_info(self, username):
        """Returns information about the specified user
        
        This call returns a JSON formatted string summarizing information about the requested user. For non-
        administrative users, only requests for the authenticated user will be accepted.
        
        Arguments:
            username(str): The username about whom to return information
            
        Returns:
            A JSON formatted string summarizing the user information
        """
        
        r = requests.get(self._base_url + "/users/%s" % username, params=self._auth)
        r.raise_for_status()
        return r.json()

    #
    # Groups resource
    # 
    def get_groups(self):
        """Fetches a list of available WebMO groups
        
        This call returns a list of available WebMO groups. For non-administrative users, this will be
        only the current authenticated group. For system administrators, this call will return all system groups.
        
        Returns:
            A list of groups
        """
        
        r = requests.get(self._base_url + "/groups", params=self._auth)
        r.raise_for_status()
        return r.json()["groups"]
        
    def get_group_info(self, groupname):
        """Returns information about the specified group
        
        This call returns a JSON formatted string summarizing information about the requested group. For non-
        administrative users, only requests for the authenticated group will be accepted.
        
        Arguments:
            groupname(str): The groupname about whom to return information
            
        Returns:
            A JSON formatted string summarizing the group information
        """
        
        r = requests.get(self._base_url + "/groups/%s" % groupname, params=self._auth)
        r.raise_for_status()
        return r.json()
        
        
    #
    # Folders resource
    # 
    def get_folders(self, target_user=""):
        """Fetches a list of folders owned by the current user or the specified target user
        
        This call returns a list of available folders. Administrative users must specify the target user,
        otherwise the folders owned by the current user are returned.
        
        Arguments:
            target_user(str, optional): The target username whose folders are retrieved. Otherwise, uses the authenticated user.
        
        Returns:
            A list of folders
        """
        
        #append other relevant paramters
        params = self._auth.copy()
        params.update({'user' : target_user})
        r = requests.get(self._base_url + "/folders", params=params)
        r.raise_for_status()
        return r.json()["folders"]
    
    #
    # Jobs resource
    #
    def get_jobs(self, engine="", status="", folder_id="", job_name="", target_user=""):
        """Fetches a list of jobs satisfying the specified filter criteria
        
        This call returns a list of available jobs owned by the current user or (for administrative users)
        the specified target user AND the specified filter criteria.
        
        Arguements:
            engine(str, optional): Filter by specified computational engine
            status(str, optional): Filter by job status
            folder_id(str, optional): Filter by folder ID (not name!)
            target_user(str, optional): The target username whose jobs are retrieved. Otherwise, uses the authenticated user.
        
        Returns:
            A list of jobs meeting the specified criteria
        """
                
        #append other relevant paramters
        params = self._auth.copy()
        params.update({'engine' : engine, 'status' : status, 'folderID' : folder_id, 'jobName' : job_name, 'user' : target_user})
        r = requests.get(self._base_url + '/jobs', params=params)
        r.raise_for_status()
        return r.json()["jobs"]
        
    def get_job_info(self, job_number):
        """Returns information about the specified job
        
        This call returns a JSON formatted string summarizing basic information about the requested job.
        
        Arguments:
            job_number(int): The job about whom to return information
            
        Returns:
            A JSON formatted string summarizing the job information
        """
        
        r = requests.get(self._base_url + "/jobs/%d" % job_number, params=self._auth)
        r.raise_for_status()
        return r.json()
        
    def get_job_results(self, job_number):
        """Returns detailed results of the calculation (e.g. energy, properties) from the specified job.
        
        This call returns a JSON formatted string summarize all of the calculated and parsed properties
        from the specified job. This information is normally summarized on the View Job page.
        
        Arguments:
            job_number(int): The job about whom to return information
            
        Returns:
            A JSON formatted string summarizing the calculated properties
        """
        
        r = requests.get(self._base_url + "/jobs/%d/results" % job_number, params=self._auth)
        r.raise_for_status()
        return r.json()
        
    def get_job_geometry(self, job_number):
        """Returns the final optimized geometry from the specified job.
        
        This call returns an XYZ formatted file of the final optimized geometry from the specified job.
        
        Arguments:
            job_number(int): The job about whom to return information
            
        Returns:
            A string containing XYZ formatted optimized geometry
        """
        
        r = requests.get(self._base_url + "/jobs/%d/geometry" % job_number, params=self._auth)
        r.raise_for_status()
        return r.json()["xyz"]
        
    def get_job_output(self, job_number):
        """Returns the raw text output from the specified job.
        
        This call returns the textual raw output file from the specified job.
        
        Arguments:
            job_number(int): The job about whom to return information
            
        Returns:
            A string containing the contents of the raw output file
        """
        
        r = requests.get(self._base_url + "/jobs/%d/raw_output" % job_number, params=self._auth)
        r.raise_for_status()
        return r.text
        
    def get_job_archive(self, job_number):
        """Returns a WebMO archive from the specified job.
        
        This call generates and returns a binary WebMO archive (tar/zip) file from the specified job.
        
        Arguments:
            job_number(int): The job about whom to generate the archive
            
        Returns:
            The raw data (as a string) of the WebMO archive, appropriate for saving to disk
        """
        
        r = requests.get(self._base_url + "/jobs/%d/archive" % job_number, params=self._auth)
        r.raise_for_status()
        return r.text
        
    def delete_job(self, job_number):
        """Permanently deletes a WebMO job 
        
        This call deletes the specified job.
        
        Arguments:
            job_number(int): The job to delete
        """
        
        r = requests.delete(self._base_url + "/jobs/%d" % job_number, params=self._auth)
        r.raise_for_status()
        
    def import_job(self, job_name, filename, engine):
        """Imports an existing output file into WebMO
        
        This call imports an existing computational output file, parsing the output and creating a newly
        WebMO job.
        
        Arguments:
            job_name(str): The name of the new WebMO job
            filename(str): The filename (full path) of an existing output file to import
            engine(str): The name of the computational engine
            
        Returns:
            The the job number of the new job, upon success
        """
        
        params = self._auth.copy()
        params.update({'jobName' : job_name, 'engine' : engine})
        output_file = {'outputFile' : ('output.log', open(filename, 'rb'), 'text/plain')}
        r = requests.post(self._base_url + '/jobs', data=params, files=output_file)
        r.raise_for_status()
        return r.json()["jobNumber"]
        
    def submit_job(self, job_name, input_file_contents, engine, queue=None):
        """Submits and executes a new WebMO job
        
        This call submits and executes a new job to a computational engine, generating a new WebMO job.
        
        Arguments:
            job_name(str): The name of the new WebMO job
            input_file_contents(str): The contents of a valid input file to submit to a computational engine
            engine(str): The name of the computational engine
            
        Returns:
            The the job number of the new job, upon success
        """
        
        params = self._auth.copy()
        params.update({'jobName' : job_name, 'engine' : engine, 'inputFile': input_file_contents, 'queue': queue})
        r = requests.post(self._base_url + '/jobs', data=params)
        r.raise_for_status()
        return r.json()["jobNumber"]
        
    def display_job_property(self, job_number, property_name, property_index=1, peak_width=0.0, tms_shift=0.0, proton_coupling=0.0, nmr_field=400.0, width=400, height=300, background_color=(255,255,255), rotate=(0.,0.,0.), filename=None):
        """Uses Javascript and IPython to display and image of the specified molecule and property,
        calculated from a previous WebMO job.
        
        This call outputs (via IPython) a PNG-formatted image of the molecule and property into the
        Jupyter notebook cell. Requires IPython and WebMO 24 or higher.
        
        Arguments:
            job_number(int): The job about whom to return information
            property_name(str): The name of the property to display. Must be one of 'geometry', 'dipole_moment', partial_charges', 'vibrational_mode', 'mo' (molecular orbital), 'esp' (electrostatic potential), 'nucleophilic', 'electrophilic', 'radical', 'nbo' (natural bonding orbital), 'nho' (natural hybrid orbital), 'nao' (natural atomic orbital), or various spectra ('ir_spectrum', 'raman_spectrum', 'vcd_spectrum', 'uvvis_spectrum', 'hnmr_spectrum', 'cnmr_spectrum')
            property_index(int, optional): The 1-based index of the property to display, e.g. which vibrational or orbital

            peak_width(float, optional): The peak width to use for spectra; default is spectrum-type specific
            tms_shift(float, optional): The chemical shift of TMS (in ppm, at same level of theory), which can be used for H1 NMR spectra
            proton_coupling(float, optional): The proton-proton coupling (in Hz), which can be used for H1 NMR spectra
            nmr_field(float, optional): The NMR field strength (in MHz), which can be used for H1 NMR spectra

            width(int, optional): The approximate width (in pixels) of the image to display (defaults to 400px)
            height(int, optional): The approximate height (in pixels) of the image to display (defaults to 300px)
            background_color(int,int,int,optional): A tuple specifying the (r,g,b) color of the background, where each color intensity is [0,255]
            rotate(int,int,int,optional): A tuple specifying the desired rotation (in degrees) of the molecule about the x,y,z axes about the "default" orientation
            filename(str, optional): Request that the displayed image is downloaded as a PNG file of the specified filename

            
        Returns:
            None
        """
        
        self._check_ipython()

        #clean up the filename; None cannot be used since this must interact with Javascript
        if filename is None:
            filename = ""
        elif not filename.endswith(".png"):
            filename += ".png"
                
        r = requests.get(self._base_url + "/jobs/%d/geometry" % job_number, params=self._auth)
        r.raise_for_status()
        geometryJSON = json.dumps(r.json())
        geometryJSON = geometryJSON.replace("\\", "\\\\")
        
        results = self.get_job_results(job_number)
        
        javascript_string = self._set_moledit_size(width,height)
        javascript_string += self._set_moledit_background(background_color[0],background_color[1],background_color[2])
        javascript_string += self._set_moledit_geometry(geometryJSON)
        
        if property_index <= 0:
            raise ValueError("Invalid property_index specified")
        
        property_string = ""
        WAVEFUNCTION_PROPERTIES = ["mo", "nao", "nho", "nbo", "esp", "nucleophilic", "electrophilic", "radical"]
        SURFACE_PROPERTIES = ["esp", "nucleophilic", "electrophilic", "radical"]
        if property_name == "geometry":
            #do nothing special
            pass

        elif property_name == "dipole_moment":
            dipole_moment = results['properties']['dipole_moment']
            total_dipole = math.sqrt(dipole_moment[0]**2 + dipole_moment[1]**2 + dipole_moment[2]**2)
            property_string = "%f:%f:%f:%f" % (*dipole_moment,total_dipole)
            javascript_string += self._set_moledit_dipole_moment(property_string)
            
        elif property_name == "partial_charges":
            partial_charges = results['properties']['partial_charges']['mulliken']
            for i in range(len(partial_charges)):
                property_string += "%d,X,%f:" % (i+1,partial_charges[i])
            property_string = property_string.rstrip(":")
            javascript_string += self._set_moledit_partial_charge(property_string)
            
        elif property_name == "vibrational_mode":
            frequency = results['properties']['vibrations']['frequencies'][property_index-1]
            displacements = results['properties']['vibrations']['displacement'][property_index-1]
            for i in range(len(displacements)//3):
                property_string += "%d,%f,%f,%f:" % (i+1,displacements[i*3+0],displacements[i*3+1],displacements[i*3+2])
            property_string = property_string.rstrip(":")
            javascript_string += self._set_moledit_vibrational_mode(property_string, property_index, frequency, 1.0)
            
        elif property_name in WAVEFUNCTION_PROPERTIES:
            if property_name in SURFACE_PROPERTIES:
                property_index = 0 #this is required
            javascript_string += self._rotate_moledit_view(rotate[0],rotate[1],rotate[2])
            javascript_string += self._set_moledit_wavefunction(job_number, property_name, property_index, filename) #handles screenshot in callback
            
        elif property_name in ["ir_spectrum", "raman_spectrum", "vcd_spectrum"]:
            frequencies = results['properties']['vibrations']['frequencies']
            if property_name == "ir_spectrum":
                intensities = results['properties']['vibrations']['intensities']['IR']
            elif property_name == "raman_spectrum":
                intensities = results['properties']['vibrations']['intensities']['raman']
            else:
                intensities = results['properties']['vibrations']['intensities']['VCD']

            for i in range(len(frequencies)):
                property_string += "%d,-,%f,%f:" % (i+1,frequencies[i],intensities[i])
            property_string = property_string.rstrip(":")

            if property_name == "ir_spectrum":
                javascript_string += self._set_datagrapher_ir_spectrum(property_string, peak_width if peak_width > 0 else 40.0)
            elif property_name == "raman_spectrum":
                javascript_string += self._set_datagrapher_raman_spectrum(property_string, peak_width if peak_width > 0 else 40.0)
            else:
                javascript_string += self._set_datagrapher_vcd_spectrum(property_string, peak_width if peak_width > 0 else 40.0)

        elif property_name == "uvvis_spectrum":
            transition_energies = results['properties']['excited_states']['transition_energies']
            intensities = results['properties']['excited_states']['intensities']
            units = results['properties']['excited_states']['units']

            for i in range(len(transition_energies)):
                property_string += "%d,-,%f,%f:" % (i+1,transition_energies[i],intensities[i])
            property_string = property_string.rstrip(":")

            javascript_string += self._set_datagrapher_uvvis_spectrum(property_string, units, peak_width if peak_width > 0 else 20.0)

        elif property_name == "hnmr_spectrum" or property_name == "cnmr_spectrum":
            symbols = results['symbols']
            isotropic = results['properties']['nmr_shifts']['isotropic']
            anisotropy = results['properties']['nmr_shifts']['anisotropy']

            for i in range(len(isotropic)):
                if tms_shift > 0 and symbols[i] == "H":
                    isotropic[i] = tms_shift - isotropic[i] #apply the TMS shift, if provided
                property_string += "%d,%s,%f,%f:" % (i+1,symbols[i],isotropic[i],anisotropy[i])
            property_string = property_string.rstrip(":")

            atom_type = "C" if property_name == "cnmr_spectrum" else "H"
            peak_width  = peak_width if peak_width > 0 else 0.001
            relative_spectrum = 1 if tms_shift > 0 and atom_type == "H" else 0

            if atom_type == "H" and proton_coupling > 0:
                javascript_string += self._set_datagrapher_h1nmr_spectrum(property_string, peak_width, proton_coupling, nmr_field, relative_spectrum)
            else:
                javascript_string += self._set_datagrapher_nmr_spectrum(property_string, atom_type, peak_width, relative_spectrum)

        else:
            raise ValueError("Invalid property_name specified")
        
        if not property_name in WAVEFUNCTION_PROPERTIES: #these are already done in the setWavefunction callback
            if property_name.endswith("spectrum"):
                javascript_string += self._display_datagrapher_screenshot(filename)
            else:
                javascript_string += self._rotate_moledit_view(rotate[0],rotate[1],rotate[2])
                javascript_string += self._display_moledit_screenshot(filename)

        display(Javascript("_call_when_ready(function(){%s})" % javascript_string))

        
    #
    # Status resource
    #
    def get_status_info(self):
        """Returns information about the specified WebMO instance
        
        This call returns a JSON formatted string summarizing basic status information about the specified WebMO instance.
        
        Arguments:
            None
            
        Returns:
            A JSON formatted string summarizing the status information
        """
        
        r = requests.get(self._base_url + "/status", params=self._auth)
        r.raise_for_status()
        return r.json()
        
        
    #
    # Helper functions
    #
    def wait_for_job(self, job_number, poll_frequency=5):
        """Waits for completion of the specified WebMO job
        
        This call blocks until the specified WebMO job has finished executing (successfully or not)
        
        Arguments:
            job_number(int): The job number to wait for
            poll_frequency(int, optional): The frequency at which to check the job status (default is 5s)
        """
        
        self.wait_for_jobs([job_number], poll_frequency)
    
    def wait_for_jobs(self, job_numbers, poll_frequency=5):
        """Waits for completion of the specified list of WebMO jobs
        
        This call blocks until the specified WebMO jobs have all finished executing (successfully or not)
        
        Arguments:
            job_numbers(list): A list of job numbers which will be waited upon
            poll_frequency(int, optional): The frequency at which to check the job status (default is 5s)
        """
        
        status = {}
        done = False
        
        for job_number in job_numbers:
            status[job_number] = ''

        while not done:
            done = True
            for job_number in job_numbers:
                if status[job_number] != 'complete' and status[job_number] != 'failed':
                    status[job_number] = self.get_job_info(job_number)['properties']['jobStatus']
                    if status[job_number] != 'complete' and status[job_number] != 'failed':
                        done = False
            if not done:
                time.sleep(poll_frequency)
            
    #
    # Private helper methods
    #
    
    def _inject_javascript(self):
        if self._init_javascript:
            config = self.get_status_info()
            major_version = int(config["version"].split(".")[0])
            
            #ensure WebMO support as well, otherwise disable IPython features
            if major_version < 24:
                global has_ipython
                has_ipython = False
                return
                
            try:
                ipython = get_ipython()
                ipython.run_cell_magic("html", "", "\
                <script src='%s/javascript/jquery.js'></script>\
                <script src='%s/javascript/moledit_js/moledit_js.nocache.js'></script>\
                <script src='%s/javascript/jupyter_moledit.js'></script>\
                <script>\
                    if(document.getElementById('moledit-panel'))\
                        document.getElementById('moledit-panel').remove();\
                    if(document.getElementById('datagrapher-panel'))\
                        document.getElementById('datagrapher-panel').remove();\
                    moledit_div = document.createElement('div');\
                    moledit_div.innerHTML = \"<DIV ID='moledit-panel' CLASS='gwt-app' STYLE='width:300px; height:300px; visibility: hidden; position: absolute' orbitalSrc='%s/get_orbital.cgi' viewOnly='true' isJupyter='true'></DIV><DIV ID='datagrapher-panel' CLASS='gwt-app' STYLE='width: 300px; height: 300px; visibility: hidden; position: absolute'></DIV>\";\
                    document.body.prepend(moledit_div);\
                    window.moledit_init_time = Date.now();\
                    function _call_when_ready(func) {\
                        const ready = document.getElementById('moledit-panel').children.length > 0 && document.getElementById('datagrapher-panel').children.length > 0;\
                        if (!ready) {\
                            setTimeout(function() {_call_when_ready(func)}, 100);\
                            return;\
                        }\
                        try {\
                            func();\
                        }\
                        catch(e) {\
                            console.log(e);\
                            setTimeout(function() {_call_when_ready(func)}, 1000);\
                        }\
                    }\
                </script>" % (config['url_html'], config['url_html'], config['url_html'], config['url_cgi']))
                self._init_javascript = False
            except:
                has_ipython = False
            	        	
    def _check_ipython(self):
        if not has_ipython:
            raise NotImplementedError("IPython and WebMO 24+ are required for this feature")
        
    def _set_moledit_geometry(self,geometryJSON):
        return "_set_moledit_geometry('%s');" % geometryJSON
        
    def _set_moledit_dipole_moment(self, value):
        return "_set_moledit_dipole_moment('%s');" % value
        
    def _set_moledit_partial_charge(self, value):
        return "_set_moledit_partial_charge('%s');" % value
        
    def _set_moledit_vibrational_mode(self, value, mode, freq, scale):
        return "_set_moledit_vibrational_mode('%s', %d, %f, %f);" % (value, mode, freq, scale)
    
    def _set_moledit_wavefunction(self, job_number, wavefunction_type, mo_index, filename):
        return "_set_moledit_wavefunction(%d,'%s', %d, element, '%s');" % (job_number, wavefunction_type, mo_index, filename)
        
    def _set_datagrapher_ir_spectrum(self, value, peak_width):
        return "_set_datagrapher_ir_spectrum('%s', %f);" % (value, peak_width)

    def _set_datagrapher_raman_spectrum(self, value, peak_width):
        return "_set_datagrapher_raman_spectrum('%s', %f);" % (value, peak_width)

    def _set_datagrapher_vcd_spectrum(self, value, peak_width):
        return "_set_datagrapher_vcd_spectrum('%s', %f);" % (value, peak_width)

    def _set_datagrapher_uvvis_spectrum(self, value, units, peak_width):
        return "_set_datagrapher_uvvis_spectrum('%s', '%s', %f);" % (value, units, peak_width)

    def _set_datagrapher_nmr_spectrum(self, value, atom_type, peak_width, relative_spectrum):
        return "_set_datagrapher_nmr_spectrum('%s', '%s', %f, %d);" % (value, atom_type, peak_width, relative_spectrum)

    def _set_datagrapher_h1nmr_spectrum(self, value, peak_width, proton_coupling, nmr_field, relative_spectrum):
        return "_set_datagrapher_h1nmr_spectrum('%s', %f, %f, %f, %d);" % (value, peak_width, proton_coupling, nmr_field, relative_spectrum)

    def _set_moledit_size(self,width,height):
        return "_set_moledit_size(%d,%d);" % (width, height)
        
    def _set_moledit_background(self,r,g,b):
        return "_set_moledit_background(%d,%d,%d);" % (r, g, b)
        
    def _rotate_moledit_view(self,rx,ry,rz):
         return "_rotate_moledit_view(%f,%f,%f);" % (rx, ry, rz)
            
    def _display_moledit_screenshot(self, filename):
        return "_display_moledit_screenshot(element, '%s');" % filename

    def _display_datagrapher_screenshot(self, filename):
        return "_display_datagrapher_screenshot(element, '%s');" % filename
