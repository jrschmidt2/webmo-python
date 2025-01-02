def xyz_from_name(name):
    """Obtains an XYZ-formatted geometry for the molecule name via PubChem lookup.

    Arguments:
        name(str): The name of the molecule.

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
        x = float(atom.x)
        y = float(atom.y)
        z = float(atom.z)
        geom += f"{element}\t{x:f}\t{y:f}\t{z:f}\n"
        
    return geom

def get_energy(results, include_units=False):
    """Returns the molecular energy from the job results. This should correspond to the ground state energy
    at molecule at the requested level of theory.

    Arguments:
        dict(results): A dictionary of job results, obtained from get_job_results.
        bool(include_units): Whether to include the units with the returned energy (e.g. 1.5 vs. "1.5 Hartree")

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
        dict(results): A dictionary of job results, obtained from get_job_results.
        bool(include_units): Whether to include the units with the returned energy (e.g. 1.5 vs. "1.5 Hartree")

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
        dict(results): A dictionary of job results, obtained from get_job_results.

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
        dict(results): A dictionary of job results, obtained from get_job_results.

    Returns:
        The stoichiometry as a string.
    """

    properties = results['properties']
    return properties['stoichiometry']

def get_dipole_moment(results):
    """Returns the dipole moment from the job results.

    Arguments:
        dict(results): A dictionary of job results, obtained from get_job_results.

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
        dict(results): A dictionary of job results, obtained from get_job_results.
        str(property_name): The name of the desired property

    Returns:
        The value of the calculated property (scalar or dictionary).
    """

    properties = results['properties']
    return properties[property_name]
