import requests
import json
import time
from getpass import getpass

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
        
    def __del__(self):
        """Destructor for WebMOREST
        
        This destructor automatically deletes the session token using the REST interface
        """
        
        #End the REST ssessions
        r = requests.delete(self._base_url + '/sessions', params=self._auth)
        #do not raise an exception for a failed request in this case due to issues
        #with object managment in Jupyter (i.e. on code re-run, a new token is made
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
            

