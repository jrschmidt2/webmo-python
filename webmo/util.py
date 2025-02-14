import numpy as np

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


def get_bond_length(results, index1, index2):
    """Returns the specified bond length between two atoms from the job results.

    Arguments:
        dict(results): A dictionary of job results, obtained from get_job_results.
        index1(int): The one-based index of the first atom of the bonded pair
        index2(int): The one-based index of the second atom of the bonded pair

    Returns:
        The calculated bond length.
    """

    geom = results['geometry']

    #convert to 0 index
    index1 -= 1
    index2 -= 1

    atom1 = np.array(geom[index1*3:index1*3 + 3])
    atom2 = np.array(geom[index2*3:index2*3 + 3])

    return np.linalg.norm(atom1 - atom2)

def get_bond_angle(results, index1, index2, index3):
    """Returns the specified bond angle between three atoms from the job results.

    Arguments:
        dict(results): A dictionary of job results, obtained from get_job_results.
        index1(int): The one-based index of the first atom
        index2(int): The one-based index of the second atom
        index3(int): The one-based index of the third atom

    Returns:
        The calculated bond angle.
    """

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
    """Returns the specified dihedral angle between four atoms from the job results.

    Arguments:
        dict(results): A dictionary of job results, obtained from get_job_results.
        index1(int): The one-based index of the first atom
        index2(int): The one-based index of the second atom
        index3(int): The one-based index of the third atom
        index4(int): The one-based index of the fourth atom

    Returns:
        The calculated dihedral angle.
    """

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

    n1 = np.cross(b1, b2)
    n2 = np.cross(b2, b3)
    n3 = np.cross(n1, n2)

    n1 /= np.linalg.norm(n1)
    n2 /= np.linalg.norm(n2)
    n3 /= np.linalg.norm(n3)

    angle = np.arccos(np.dot(n1,n2))*180./np.pi
    if np.dot(b2,n3) > 0:
        angle = -angle

    return angle
