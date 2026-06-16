import numpy as np

def xyz_from_name(name, include_atomic_number=False):
    """Obtains an XYZ-formatted geometry for the molecule name via PubChem lookup.

    Arguments:
        name(str): The name of the molecule.
        include_atomic_number(bool): Whether to include the atomic number as well in the XYZ output (e.g. for GAMESS formatted Cartesian coordinates)

    Returns:
        A string containing the molecule's XYZ-formatted geometry.
    """
    import pubchempy as pcp

    results = pcp.get_compounds(name, 'name', record_type='3d')
    if (len(results) == 0):
        raise ValueError("Specified molecule could not be found in PubChem")

    record = results[0]
    geom = ""
    for atom in record.atoms:
        element = atom.element
        number = int(atom.number)
        x = float(atom.x)
        y = float(atom.y)
        z = float(atom.z)
        if include_atomic_number:
            geom += f"{element}\t{number:d}\t{x:f}\t{y:f}\t{z:f}\n"
        else:
            geom += f"{element}\t{x:f}\t{y:f}\t{z:f}\n"
        
    return geom

def get_energy(results, include_units=False):
    """Returns the molecular energy from the job results. This should correspond to the ground state energy
    at molecule at the requested level of theory.

    Requires WebMO 25 or higher.

    Arguments:
        results(dict): A dictionary of job results, obtained from get_job_results.
        include_units(bool): Whether to include the units with the returned energy (e.g. 1.5 vs. "1.5 Hartree")

    Returns:
        The molecular energy.
    """
    properties = results['properties']

    if not 'method_energy_name' in properties.keys():
        raise RuntimeError('Cannot locate "method_energy_name" in results')
    method_energy_name = properties['method_energy_name'].lower().replace(' ', '_') + '_energy'

    found = False
    #also check related key names, since Gaussian prepends some things occasionally
    for key in [method_energy_name, 'r' + method_energy_name, 'u' + method_energy_name, 'ro' + method_energy_name]:
        if key in properties:
            energy = properties[key]['value']
            units = properties[key]['units']
            found = True

    if not found:
        raise RuntimeError('Could not locate "' + method_energy_name + '" in results')

    if include_units:
        energy = f"{energy} {units}"

    return energy

def get_energies(results, include_units=False):
    """Returns a dictionary of available energies from the job results.

    Arguments:
        results(dict): A dictionary of job results, obtained from get_job_results.
        include_units(bool): Whether to include the units with the returned energy (e.g. 1.5 vs. "1.5 Hartree")

    Returns:
        A dictionary of available energies.
    """
    properties = results['properties']
    energies = {}

    for key in properties.keys():
        index = key.find('_energy')

        if key.endswith('_energy'):
            index = key.find('_energy')
            energy_type = key[:index]

            if include_units:
                energies[energy_type] = f"{properties[key]['value']} {properties[key]['units']}"
            else:
                energies[energy_type] = properties[key]['value']

    return energies

def get_geometry(results):
    """Returns the XYZ-formatted final geometry from the job results.

    Arguments:
        results(dict): A dictionary of job results, obtained from get_job_results.

    Returns:
        The XYZ-formatted final geometry as a string.
    """


    geom = ""
    index = 0
    for element in results['symbols']:

        x = results['geometry'][index]
        y = results['geometry'][index + 1]
        z = results['geometry'][index + 2]

        geom += f"{element}\t{x:f}\t{y:f}\t{z:f}\n"
        index += 3

    return geom

def get_stoichiometry(results):
    """Returns the stoichiometry from the job results.

    Arguments:
        results(dict): A dictionary of job results, obtained from get_job_results.

    Returns:
        The stoichiometry as a string.
    """

    properties = results['properties']
    return properties['stoichiometry']

def get_dipole_moment(results):
    """Returns the dipole moment from the job results.

    Arguments:
        results(dict): A dictionary of job results, obtained from get_job_results.

    Returns:
        The magnitude of the dipole moment.
    """

    from math import sqrt

    properties = results['properties']
    dipole = properties['dipole_moment']
    mag = sqrt(dipole[0]**2 + dipole[1]**2 + dipole[2]**2)

    return mag

def get_property(results, property_name):
    """Returns an arbitrary calculated property from the job results.

    Arguments:
        results(dict): A dictionary of job results, obtained from get_job_results.
        property_name(str): The name of the desired property

    Returns:
        The value of the calculated property (scalar or dictionary).
    """

    properties = results['properties']
    return properties[property_name]


def get_bond_length(results, index1, index2):
    """Returns the specified bond length between two atoms from the job results OR an xyz-formatted string.

    Arguments:
        dict(results): A dictionary of job results obtained from get_job_results OR an xyz-formatted string.
        index1(int): The one-based index of the first atom of the bonded pair
        index2(int): The one-based index of the second atom of the bonded pair

    Returns:
        The calculated bond length.
    """

    if not isinstance(results, dict):
        geom = _xyz_to_array(results)
    else:
        geom = results['geometry']

    #convert to 0 index
    index1 -= 1
    index2 -= 1

    atom1 = np.array(geom[index1*3:index1*3 + 3])
    atom2 = np.array(geom[index2*3:index2*3 + 3])

    return np.linalg.norm(atom1 - atom2)

def get_bond_angle(results, index1, index2, index3):
    """Returns the specified bond angle between three atoms from the job results OR an xyz-formatted string.

    Arguments:
        dict(results): A dictionary of job results obtained from get_job_results OR an xyz-formatted string.
        index1(int): The one-based index of the first atom
        index2(int): The one-based index of the second atom
        index3(int): The one-based index of the third atom

    Returns:
        The calculated bond angle.
    """

    if not isinstance(results, dict):
        geom = _xyz_to_array(results)
    else:
        geom = results['geometry']

    #convert to 0 index
    index1 -= 1
    index2 -= 1
    index3 -= 1

    atom1 = np.array(geom[index1*3:index1*3 + 3])
    atom2 = np.array(geom[index2*3:index2*3 + 3])
    atom3 = np.array(geom[index3*3:index3*3 + 3])

    vec1 = atom1 - atom2
    vec2 = atom3 - atom2

    vec1 /= np.linalg.norm(vec1)
    vec2 /= np.linalg.norm(vec2)

    return np.arccos(np.dot(vec1,vec2))*180./np.pi

def get_dihedral_angle(results, index1, index2, index3, index4):
    """Returns the specified dihedral angle between four atoms from the job results OR an xyz-formatted string.

    Arguments:
        dict(results): A dictionary of job results obtained from get_job_results OR an xyz-formatted string.
        index1(int): The one-based index of the first atom
        index2(int): The one-based index of the second atom
        index3(int): The one-based index of the third atom
        index4(int): The one-based index of the fourth atom

    Returns:
        The calculated dihedral angle.
    """

    if not isinstance(results, dict):
        geom = _xyz_to_array(results)
    else:
        geom = results['geometry']

    #convert to 0 index
    index1 -= 1
    index2 -= 1
    index3 -= 1
    index4 -= 1

    atom1 = np.array(geom[index1*3:index1*3 + 3])
    atom2 = np.array(geom[index2*3:index2*3 + 3])
    atom3 = np.array(geom[index3*3:index3*3 + 3])
    atom4 = np.array(geom[index4*3:index4*3 + 3])

    b1 = atom1 - atom2
    b2 = atom2 - atom3
    b3 = atom3 - atom4

    b1 /= np.linalg.norm(b1)
    b2 /= np.linalg.norm(b2)
    b3 /= np.linalg.norm(b3)

    n1 = np.cross(b1, b2)
    n2 = np.cross(b2, b3)
    m = np.cross(n1, b2)

    x = np.dot(n1, n2)
    y = np.dot(m, n2)

    return np.arctan2(y, x)*180./np.pi

def get_option_matching(template, variable, desired_value_aliases, ignore_missing_variables=False):
    """Returns the best matching template variable option for the specified variable.

    This can be useful when an engine uses non-standard names for options and you want to use a
    more descriptive name (like that shown in the dropdown) rather than the corresponding value. It attempts
    to match either the corresponding option value (if it exists) OR the description.

    For example:
        get_option_matching(template, 'basisSet', '6-31G(d)')
    will return the value:
        "N31 NGAUSS=6 NDFUNC=1"
    since it matches the corresponding option description "Routine: 6-31G(d)" in the dropdown.

    Arguments:
        template(dict): The desired job template (from get_templates)
        variable(str): The template variable
        desired_value_aliases(list): A list of potentially matching values, or aliases thereof; a single string is also acceptable.
        ignore_missing_variables(bool, opt): Whether to raise an exception if the template variable does not exist in the template

    Returns:
        The best matching corresponding variable value
    """

    def ends_with_whole_word(text, target_word):
        # Check if it ends with the word
        if not text.endswith(target_word):
            return False
        # Get the start index of the target word in the text
        idx = len(text) - len(target_word)
        # If it's at the very beginning of the string, it's a whole word
        if idx == 0:
            return True
        # Check if the character just before our word is a space or a colon
        return text[idx - 1].isspace() or text[idx - 1] == ':'

    #immediately return if the desired value is blank (for some reason)
    if isinstance(desired_value_aliases, str) and not desired_value_aliases.strip():
        return ""

    #normalize any scalar arguement ot a list
    if not isinstance(desired_value_aliases, list):
        desired_value_aliases = [desired_value_aliases]
    #immediately return if this variable does not exist in this particular template
    if not variable in template['variables']:
        if ignore_missing_variables:
            return ""
        else:
            raise ValueError(f"Could not locate variable {variable} in template")
    #ensure that the template variable is a 'dropdown' type
    if template['variables'][variable]['type'] != 'dropdown':
        raise ValueError(f"Template variable {variable} is not of type dropdown")

    options = template['variables'][variable]['options']
    for desired_value in desired_value_aliases:
        for key, value in options.items():
            #check if the specified value exists as value in the options dictionary
            if value.casefold() == desired_value.casefold():
                return value
            #otherwise check if it matches the end of any key in the dictionary
            if ends_with_whole_word(key.casefold(), desired_value.casefold()):
                return options[key]

    #not found!
    raise ValueError(f"Could not locate option {desired_value_aliases} for template variable {variable}")


def _xyz_to_array(xyz):
    xyz = xyz.strip()

    try:
        #throw exception if NOT a number, indicating that our XYZ file has no header
        tokens = xyz.split()
        int(tokens[0])
        #this XYZ formatted string is proper, containing a header that must be removed
        xyz = xyz.split("\n",2)[2]
    except ValueError:
        pass

    #process the actual geometry of the XYZ file, converting into an array
    geom = xyz.split()
    #remove the element names, leaving only an array of positions
    del geom[0::4]

    #convert to an array of floats and return
    return np.array(geom,dtype=float)
