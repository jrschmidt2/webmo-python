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
