# -*- coding: utf-8 -*-

import numpy as np
import warnings
import string
import collections
import itertools

def despeckle(M, stds=2, width=2):
   """Replaces outstanding values (above stds standard deviations) in a matrix 
   by the average of a surrounding window of desired width."""
   N = np.copy(M)
   n,m = M.shape
   for i in range(stds,n-stds):
       for j in range(stds,m-stds):
           square = M[i-width:i+width,j-width:j+width]
           avg = np.average(square)
           std = np.std(square)
           if M[i,j] >= avg + stds*std:
               N[i,j] = avg
   return (N+N.T)/2

def bin_dense(M,subsampling_factor=3):
    """Sums over each block of given subsampling factor, returns a matrix whose
    dimensions are this much as small (e.g. a 27x27 matrix binned with a 
    subsampling factor equal to 3 will return a 9x9 matrix whose each component
    is the sum of the corresponding 3x3 block in the original matrix). 
    Remaining columns and rows are summed likewise and added to the end of the 
    new matrix.
    
    NOTE: Will not work for numpy verisons below 1.7"""   
    m = min(M.shape)
    n = (m//subsampling_factor)*subsampling_factor
    
    if n == 0:
        return np.array([M.sum()])
    
    N = M[:n,:n]
    N = N.reshape(n//subsampling_factor, subsampling_factor, 
        n//subsampling_factor, subsampling_factor).sum(axis=(1, 3))
    if m > n:
        remaining_row = M[n:,:n]
        remaining_col = M[:n,n:]
        remaining_square = M[n:m,n:m]
        R = remaining_row.reshape(m%subsampling_factor,m//subsampling_factor, 
                              subsampling_factor).sum(axis=(0,2))
        C = remaining_col.T.reshape(m%subsampling_factor,m//subsampling_factor, 
                              subsampling_factor).sum(axis=(0,2)).T
        S = remaining_square.sum()
        N = np.append(N,[R],axis=0)
        O = np.append(N,np.array([list(C)+[S]]).T,axis=1)
    else:
        print("Nothing to do.")
        O = N
        
    return O
    
def bin_sparse(M,subsampling_factor=3):
    """Performs the bin_dense procedure for sparse matrices. Remaining rows
    and cols are lumped with the rest at the end."""

    try:
        from scipy.sparse import coo_matrix
    except ImportError as e:
        print(str(e))
        print("I am peforming dense binning by default.")
        return bin_dense(M.todense())

    N = M.tocoo()
    n,m = N.shape
    row,col,data=N.row,N.col,N.data
    
    #Divide row and column indices - duplicate coordinates are added in 
    #sparse matrix construction    
    
    binned_row = row//subsampling_factor
    binned_col = col//subsampling_factor
    binned_n = n//subsampling_factor
    binned_m = m//subsampling_factor
    
    #Attach remaining columns and rows to the last one   
    
    binned_row[binned_row>=binned_n] -= n%subsampling_factor
    binned_col[binned_col>=binned_m] -= m%subsampling_factor
    
    O = coo_matrix((data,(binned_row,binned_col)),shape=(binned_n,binned_m))
    return O

def bin_matrix(M,subsampling_factor=3):
    """Bins either sparse or dense matrices."""
    try:
        from scipy.sparse import issparse
        if issparse(M):
            return bin_sparse(M,subsampling_factor=subsampling_factor)
        else:
            raise ImportError
    except ImportError:
        return bin_dense(M,subsampling_factor=subsampling_factor)
        
def bin_annotation(annotation=None,subsampling_factor=3):
    """Performs binning on genome annotations such as contig information or bin
    positions."""
    if annotation is None:
        annotation = np.array([])
    n = len(annotation)
    binned_positions = [annotation[i] for i in range(n) if
    i%subsampling_factor==0]
    if len(binned_positions) == 0:
        binned_positions.append(0)
    return np.array(binned_positions)
    
def bin_measurement(measurement=None,subsampling_factor=3):
    """Performs binning on genome-wide measurements by summing each component
    in a window of variable size (subsampling_factor)."""
    if measurement is None:
        measurement = np.array([])
    n = len(measurement)
    binned_measurement = [measurement[i-subsampling_factor+1:i].sum() for i in
    range(n) if i%subsampling_factor==0 and i>0]
    return np.array(binned_measurement)
    
def build_pyramid(M,subsampling_factor=3):
    """Iterates over a given number of times on matrix M so as to compute 
    smaller and smaller matrices with bin_dense."""
    if not (subsampling_factor > 1 and int(subsampling_factor)==subsampling_factor):
        raise ValueError("Subsampling factor needs to be an integer greater than 1.")
    N = [M]
    while min(N[-1].shape) > 1:
        N.append(bin_matrix(N[-1],subsampling_factor=subsampling_factor))
    return N
    
def bin_kb_dense(M,positions,length=10,contigs=None):
    """Performs binning with a fixed genomic length in kilobase pairs (kb). 
    Fragments will be binned such that their total length is closest to the 
    specified input. If a contig list is specified, binning will be performed 
    such that fragments never overlap two contigs."""
    unit = 10**3
    l = unit*length
    unit = positions/l
    n = len(positions)
    indices = [i for i in range(n-1) if np.ceil(unit[i]) < np.ceil(unit[i+1])]
    binned_positions = positions[indices]
    m = len(indices)-1
    N = np.zeros((m,m))
    for i in range(m):
        N[i] = np.array([M[indices[j]:indices[j+1],indices[i]:indices[i+1]].sum() for j in range(m)])                
            
    return N,binned_positions

def bin_exact_kb_dense(M,positions,length=10):
    """Performs the kb-binning procedure with total bin lengths being exactly
    set to that of the specified input. Fragments overlapping two potential 
    bins will be split and related contact counts will be divided according 
    to overlap proportions in each bin. """
    unit = 10**3
    l = unit*length
    units = positions/l
    n = len(positions)
    indices = [i for i in range(n-1) if np.ceil(units[i]) < np.ceil(units[i+1])]
    m = len(indices)-1
    N = np.zeros((m,m))
    remainders = [0]+[np.abs(units[i]-units[i+1]) for i in range(m)]
    for i in range(m):
        N[i] = np.array([M[indices[j]:indices[j+1],indices[i]:indices[i+1]].sum()-remainders[j]*M[i][j]+remainders[j+1]*M[i+1][j] for j in range(m)])    
    return N
    
def bin_kb_sparse(M,positions,length=10):
    """Performs the exact kb-binning procedure on a sparse matrix."""
    try:
        from scipy.sparse import coo_matrix
    except ImportError as e:
        print(str(e))
        print("I am peforming dense normalization by default.")
        return bin_kb_dense(M.todense())
    r = M.tocoo()
    unit = 10**3
    l = unit*length
    units = positions/l
    n = len(positions)
    indices = np.floor(units)
    row = [indices[np.floor(i)] for i in r.row/l]
    col = [indices[np.floor(j)] for j in r.col/l]
    binned_indices = positions[[i for i in range(n-1) if np.ceil(units[i]) < np.ceil(units[i+1])]]
    return coo_matrix((r.data,(row,col))), binned_indices
    
def trim_dense(M, n_std=3, s_min=None, s_max=None):
    """By default, returns a matrix stripped of component vectors whose 
    sparsity (i.e. total contact count on a single column or row) deviates 
    more than specified number of standard deviations from the mean. Boolean 
    variables s_min and s_max act as absolute fixed values which override such 
    behaviour when specified."""
    
    M = np.array(M)
    sparsity = M.sum(axis=1)
    mean = np.mean(sparsity)
    std = np.std(sparsity)
    if s_min is None:
        s_min = mean-n_std*std
    if s_max is None:
        s_max = mean+n_std*std
    elif s_max == 0:
        s_max = np.amax(M)
    f = (sparsity>s_min)*(sparsity<s_max)
    N = M[f][:,f]
    return N
    
def trim_sparse(M, n_std=3, s_min=None,s_max=None):
    """Applies the trimming procedure to a sparse matrix."""
    try:
        from scipy.sparse import coo_matrix
    except ImportError as e:
        print(str(e))
        print("I am peforming dense normalization by default.")
        return trim_dense(M.todense())
    r = M.tocoo()
    sparsity = np.array(r.sum(axis=1)).flatten()
    mean = np.mean(sparsity)
    std = np.std(sparsity)
    if s_min is None:
        s_min = mean-n_std*std
    if s_max is None:
        s_max = mean+n_std*std
    f = (sparsity>s_min)*(sparsity<s_max)
    indices = [u for u in range(len(r.data)) if f[r.row[u]] and f[r.col[u]]]
    rows = np.array([r.row[i] for i in indices])
    cols = np.array([r.col[j] for j in indices])
    data = np.array([r.data[k] for k in indices])

    N = coo_matrix((data,(rows,cols)))
    return N

def normalize_dense(M,norm="frag",order=1,iterations=3):
    """Applies one of the many normalization types to input dense matrix.
    Will also apply any callable norms such as a user-made or a lambda function.
    """
    
    s = np.copy(M)
    floatorder = np.float64(order)    
    
    if norm == "SCN":
        for iteration in range(1,iterations):
            sumrow = s.sum(axis=1)
            sumcols = s.sum(axis=0)
            s[sumrow!=0][:,sumrow!=0] = s[sumrow!=0][:,sumrow!=0]/sumrow[sumrow!=0]
            s[sumcols!=0][:,sumcols!=0] = s[sumcols!=0][:,sumcols!=0]/sumcols[sumcols!=0]        
        
    elif norm == "mirnylib":
        try:        
            from mirnylib import numutils as ntls
            s = ntls.iterativeCorrection(s, iterations)[0]
        except ImportError as e:
            print(str(e))
            print("I can't find mirnylib.")
            print("Please install it from https://bitbucket.org/mirnylab/mirnylib")
            raise
            
    elif norm == "frag":
        for iteration in range(1,iterations):
            s_norm_x = np.linalg.norm(s, ord=floatorder, axis=0)
            s_norm_y = np.linalg.norm(s, ord=floatorder, axis=1)
            s_norm = np.tensordot(s_norm_x,s_norm_y,axes=0)
            s[s_norm!=0] = s[s_norm!=0]/s_norm[s_norm!=0]
    
    elif norm == "global":
        s_norm = np.linalg.norm(s, ord=floatorder)
        s /= s_norm
        
    elif callable(norm):
        s = norm(M)
        
    else:
        print("I don't recognize this norm, I am returning input matrix by default.")
        
    return (s+s.T)/2    
    
def normalize_sparse(M,norm="frag",order=1,iterations=3):
    """Applies a normalization type to a sparse matrix."""
    try:
        from scipy.sparse import csr_matrix
    except ImportError as e:
        print(str(e))
        print("I am peforming dense normalization by default.")
        return normalize_dense(M.todense())
    r = csr_matrix(M)
    if norm == "SCN":
        for iteration in range(1,iterations):
            row_sums = np.array(r.sum(axis=1)).flatten()
            col_sums = np.array(r.sum(axis=0)).flatten()
            row_indices, col_indices = r.nonzero()
            r.data /= row_sums[row_indices]*col_sums[col_indices]

    elif norm == "global":
        try:
            from scipy.sparse import linalg
            r = linalg.norm(M,ord=order)
        except (ImportError,AttributeError) as e:
            print(str(e))
            print("I can't import linalg tools for sparse matrices.")
            print("Please upgrade your scipy version to 0.16.0.")

    elif callable(norm):
        r = norm(M)
        
    else:
        print("I don't recognize this norm, I am returning input matrix by default.")
        
    return r
    
def directional(M, window=None, circ=False, extrapolate=True):
    """From a symmetrical matrix M of size n, return a vector d whose each 
    component d[i] is a T-test of two samples represented by vectors of size
    window on either side of the i-th pixel on the diagonal. Edge elements may 
    be extrapolated based on the vector size reduction, except in the case of 
    circular genomes. If they aren't, d will be of size n - 2*(window-1) 
    instead of n.
    """
    #Sanity checks
    if not type(M) is np.ndarray:
        M = np.array(M)

    if M.shape[0] != M.shape[1]:
        raise ValueError("Matrix is not square.")
    
    try:
        n = min(M.shape)
    except AttributeError:
        n = M.size

    #Default window argument
    if window is None:
        window = max(n//100,5)
        
    if window >= n:
        raise ValueError("Please choose a smaller window size.")
    
    try:
        from scipy.stats import ttest_rel
    except ImportError as e:
        print("I couldn't import scipy's stats module which is needed to compute directionality index.")
        print(str(e))
        raise
        
    if circ:
        d = [ttest_rel(np.array(list(M[i,i-window:])+list(M[i,:i])),M[i,i:i+window])[0] for i in range(window)]
    elif extrapolate:
        d = [ttest_rel(M[i,0:i],M[i,i:2*i])[0] for i in range(window)]
    else:
        d = []

    d += [ttest_rel(M[i,i-window:i],M[i,i:i+window])[0] for i in range(window,n-window)]
    
    if circ:
        d += [ttest_rel(M[i,i-window:i],M[i,i:i+window])[0] for i in range(window)]
    elif extrapolate:
        d += [ttest_rel(M[i,i-window:i],np.array(list(M[i,i:])+list(M[i,:window-(n-i)])))[0] for i in range(n-window,n)]
        
    return d

def domainogram(M, window=None, circ=False, extrapolate=True):
    """From a symmetrical matrix M of size n, return a vector d whose each 
    component d[i] is the total sum of a square of 2*window+1 size centered on 
    the i-th main diagonal element. Edge elements may be extrapolated based on 
    the square size reduction (i.e. for window = 4, the first component will be 
    equal to the first diagonal pixel multiplied by 81, the second one will be 
    equal to the first 2x2 square on the diagonal multiplied by 81/4, etc.),
    except in the case of circular genomes. If they aren't, d will be of size
    n - 2*(window-1) instead of n.
    """
    
    #Sanity checks
    if not type(M) is np.ndarray:
        M = np.array(M)
    
    if M.shape[0] != M.shape[1]:
        raise ValueError("Matrix is not square.")
    
    try:
        n = min(M.shape)
    except AttributeError:
        n = M.size
        
    #Default window argument
    if window is None:
        window = max(n//100,5)
        
    if window >= n:
        raise ValueError("Please choose a smaller window size.")

    if circ:
        d = [np.sum(M[-i+window:,-i+window:]) + np.sum(M[:i-window+1,:i-window+1]) for i in range(window)]
    elif extrapolate:
        d = [np.sum(M[0:2*i+1,0:2*i+1])*((2*window+1)**2.0)/((2*i+1)**2.0) for i in range(window)]
    else:
        d = []
        
    d += [np.sum(M[i-window:i+window+1,i-window:i+window+1]) for i in range(window,n-window)]
    
    if circ:
        d += [M[i:,i:].sum() + M[:n-i,n-i].sum() for i in range(n-window,n)]
    elif extrapolate:
        d += [M[i-window:,i-window:].sum()*((2*window+1)**2.0)/((2*(n-i)+1)**2.0) for i in range(n-window,n)]
        
    return np.array(d)

def from_dade_matrix(filename, header=False):
    """
    Loads a numpy array from a Dade matrix instance.
    E.g.: A matrix containing the following (or equivalent in numpy)
        [['RST','chr1~0','chr1~10','chr2~0','chr2~30'],
        ['chr1~0','5', '10', '11', '2'],
        ['chr1~10',   '8', '3', '5'],
        ['chr2~0',         '3', '5'],
        ['chr2~30',             '5']]
        
    will return: 
       [['5', '10', '11', '2'],
        ['10', '8', '3', '5'],
        [11', '3', '3', '5'],
        ['2', '5', '5', '5']], [chr1~0','chr1~10','chr2~0','chr2~30']
        
    Header data processing is delegated downstream.
    """
    A = np.genfromtxt(filename, delimiter="\t", dtype=None)
    M, headers = np.array(A[1:,1:],dtype=np.float64), A[0]
    matrix = M + M.T - np.diag(np.diag(M))
    parsed_header = list(zip(*[str(h)[:-1].strip('"').strip("'").split("~") for h in headers[1:]]))
    if header:
        return matrix, parsed_header
    else:
        return matrix
    
def to_dade_matrix(M,annotations="",filename=None):
    """Returns a Dade matrix from input numpy matrix. Any annotations are added
    as header. If filename is provided and valid, said matrix is also saved 
    as text."""
    n,m = M.shape
    A = np.zeros((n+1,m+1))
    A[1:,1:] = M
    if not annotations:
        annotations = np.array(["" for _ in n],dtype=str)
    A[0,:] = annotations
    A[:,0] = annotations.T
    if filename:
        try:
            np.savetxt(filename,A,fmt='%i%')
            print("I saved input matrix in dade format as "+str(filename))
        except ValueError as e:
            print("I couldn't save input matrix.")
            print(str(e))
        finally:
            return A

    return A
    
def from_structure(structure):
    """Return contact data from a 3D structure (in the pdb format)."""
    try:
        from Bio import PDB
        if isinstance(structure, str):
            p = PDB.PDBParser()
            structure = p.get_structure('S', structure)
        if isinstance(structure, PDB.Structure.Structure):     
            for chain in structure.get_chains():
                atoms = [np.array(atom.get_coord()) for atom in structure.get_atoms()]
    except ImportError as e:
        warnings.warn("I couldn't import Biopython. If input was a pdb file,",
        "expect things to be messy.", RuntimeWarning)
        print(str(e))
        
    atoms = np.array(structure)
    try:
        import scipy
        D = scipy.spatial.distance.pdist(atoms, 'euclidean')
        D = scipy.spatial.distance.squareform(D)
    except ImportError as e:
        print("I couldn't find scipy which is needed to compute distance matrices.")
        raise
    m = np.max(1/D[D!=0])
    M = np.zeros(D.shape)
    M[D!=0] = 1/D[D!=0]
    M[D==0] = m
    return M
    
def largest_connected_component(matrix):
    """Compute the adjacency matrix of the largest connected component of the 
    graph whose input matrix is adjacent."""
    try:
        import scipy.sparse
        n, components = scipy.sparse.csgraph.connected_components(matrix,directed=False)
        print("I found "+str(n)+" connected components.")
        component_dist = collections.Counter(components)
        print("Distribution of components: "+str(component_dist))
        most_common, n_most_common = component_dist.most_common(1)[0]
        ilcc = (components == most_common)
        return matrix[:,ilcc][ilcc]
        
    except ImportError as e:
        print("I couldn't find scipy which is needed for graph routines.")
        print(str(e))
        print("Returning input matrix as fallback.")
        return matrix
    
def to_structure(matrix, alpha=1, filename=None):
    """Compute best matching 3D genome structure from underlying input matrix 
    using ShRec3D-derived method from Lesne et al., 2014.
    
    The method performs two steps: first compute distance matrix by treating
    contact data as an adjacency graph (of weights equal to a power law function
    of the data), then embed the resulting distance matrix into 3D space.
    
    The alpha parameter influences the weighting of contacts: if alpha < 1
    long-range interactions are prioritized; if alpha >> 1 short-range
    interactions have more weight wahen computing the distance matrix.
    """
    connected = largest_connected_component(matrix)
    distances = to_distance(connected, alpha)
    n,m = connected.shape
    bary = np.sum(np.triu(distances,1))/(n**2) #barycenters
    d = np.array(np.sum(distances**2,0)/n - bary) #distances to origin
    gram = np.array([(d[i]+d[j]-distances[i][j]**2)/2 for i,j in itertools.product(range(n),range(m))]).reshape(n,m)
    normalized = gram/np.linalg.norm(gram,'fro')
    symmetric = (normalized + normalized.T)/2 #just in case
    from scipy import linalg
    eigen_values, eigen_vectors = linalg.eigh(symmetric)
    idx = eigen_values.argsort()[-3:][::-1]
    values = eigen_values[idx]
    vectors = eigen_vectors[:,idx]
    coordinates = vectors*np.sqrt(values)
    return coordinates
    
def get_missing_bins(original,trimmed):
    """Retrieve indices of a trimmed matrix with respect to the original matrix.
    Fairly fast but is only correct if diagonal values are different, which is
    always the case in practice."""
    original_diag = np.diag(original)
    trimmed_diag = np.diag(trimmed)
    index = []
    m = min(original.shape)
    for j in range(min(trimmed.shape)):
        k = 0
        while original_diag[j+k] != trimmed_diag[j] and k<2*m:
            k+=1
        index.append(k+j)
    return np.array(index)
    
def to_pdb(structure,filename,contigs=None,annotations=None,indices=None):
    """From a structure (or matrix) generate the corresponding pdb file
    representing each chain as a contig/chromosome and filling the occupancy
    field with a custom annotation. If the matrix has been trimmed somewhat,
    remaining indices may be specified.
    """
    n = len(structure)
    letters = (string.ascii_uppercase+string.ascii_lowercase+string.digits+string.punctuation)*int(n/94 +1)
    if contigs is None:
        contigs = np.ones(n+1)
    if annotations is None:
        annotations = np.zeros(n+1)
    if indices is None:
        indices = range(n+1)

    if isinstance(structure, np.ndarray) and structure.shape[0] == structure.shape[1]:
        structure = (to_structure(structure))
        
    X,Y,Z = (structure[:,i] for i in range(3))
    Xmax, Ymax, Zmax = (np.max(np.abs(Xi)) for Xi in (X,Y,Z)) 
    X *= 100.0/Xmax
    Y *= 100.0/Ymax
    Z *= 100.0/Zmax
    
    X = np.around(X,3)
    Y = np.around(Y,3)
    Z = np.around(Z,3)
    with open(filename, 'w') as f:
        for i in range(1,n):
            line = "ATOM" #1-4 "ATOM"
            line += "  " #5-6 unused
            line += str(i).rjust(5) #7-11 atom serial number
            line += " " #12 unused
            line += "OW".rjust(4) #13-16 atom name
            line += " " #17 alternate location indicator
            line += "SOL" #18-20 residue name
            line += " " #21 unused
            line += letters[int(contigs[indices[i]]-1)] #22 chain identifier
            line += str(i).rjust(4) #23-26 residue sequence number
            line += " " #27 code for insertion of residues
            line += "   " #28-30 unused
            line += str(X[i]).rjust(8) #31-38 X orthogonal Å coordinate
            line += str(Y[i]).rjust(8) #39-46 Y orthogonal Å coordinate
            line += str(Z[i]).rjust(8) #47-54 Z orthogonal Å coordinate
            line += "1.00".rjust(6) #55-60 Occupancy
            line += str(annotations[i-1]).rjust(6) #61-66 Temperature factor
            line += "      " #67-72 unused
            line += "    " #73-76 segment identifier 
            line += "O".rjust(2) #77-78 element symbol
            line += "\n"
            f.write(line)

def to_distance(matrix,alpha=1):
    """Compute distance matrix from contact data by applying a negative power
    law (alpha) to its nonzero pixels, then interpolating on the zeroes using a 
    shortest-path algorithm.
    """
    try:
        import scipy.sparse
    except ImportError as e:
        print("I can't import scipy which is required to compute distance matrices.")
        print(str(e))
        raise   
        
    if hasattr(matrix, 'getformat'):
        distances = scipy.sparse.coo_matrix(matrix)
        distances.data = 1/distances.data
    else:
        distances = np.zeros(matrix.shape)
        distances[matrix!=0] = 1/matrix[matrix!=0]**alpha

    return scipy.sparse.csgraph.floyd_warshall(distances,directed=False)
    
def distance_to_contact(D,alpha=1):
    """Compute contact matrix from input distance matrix. Distance values of
    zeroes are given the largest contact count otherwise inferred non-zero
    distance values."""
    m = np.max(1/(D[D!=0]**alpha))
    M = np.zeros(D.shape)
    M[D!=0] = 1/(D[D!=0]**alpha)
    M[D==0] = m
    return M
    
def distance_law(matrix,log_bins=False):
    """Compute distance law as a function of the genomic coordinate aka P(s).
    Bin length increases exponentially with distance if log_bins is True."""
    D = np.array([np.average(np.diagonal(matrix,j)) for j in range(min(matrix.shape))])
    if not log_bins:
        return D
    else:
        n = min(matrix.shape)
        n_bins = int(np.log(n)/np.log(2) + 1)
        logD = np.array([np.average(D[int(2**(i-1)):min(n,2**i)]) for i in range(n_bins)])
        return logD
        
def shortest_path_interpolation(matrix,alpha=1,strict=True):
    """Perform interpolation on a matrix's data by using ShRec's shortest-path
    procedure backwards and forwards. This replaces zeroes with corresponding 
    shortest-path based counts and may have the additional effect of 'blurring'
    the matrix somewhat. If strict is set to True, only zeroes are replaced this way."""
    I = distance_to_contact(to_distance(matrix,alpha=alpha),alpha=alpha)
    if not strict:
        return I
    else:
        M = np.copy(matrix)
        M[matrix==0] = I[matrix==0]
        return M
    
def pdb_to_structure(filename):
    """Import a structure object from a PDB file."""
    try:
        from Bio.PDB import PDB
    except ImportError:
        print("I can't import Biopython which is needed to handle PDB files.")
        raise
    p = PDB.PDBParser()
    structure = p.get_structure('S', filename)
    for chain in structure.get_chains():
        atoms = [np.array(atom.get_coord()) for atom in structure.get_atoms()]   
    return atoms

def noise(matrix):
    D = shortest_path_interpolation(matrix,strict=True)
    return np.random.poisson(lam=D)
    
def positions_to_contigs(positions):
    
    if isinstance(positions,np.ndarray):
        flattened_positions = positions.flatten()
    else:
        try:
            flattened_positions = [pos for contig in positions for pos in contig]
        except TypeError:
            flattened_positions = positions
            
    n = len(flattened_positions)
    contigs = np.ones(n)
    counter = 0
    for i in range(1,n):
        if positions[i] == 0:
            counter += 1
            contigs[i] += counter
        else:
            contigs[i] = contigs[i-1]
    return contigs
    
def distance_diagonal_law(matrix, positions=None):
    return np.array([np.average(np.diagonal(matrix,j)) for j in range(min(matrix.shape))])

def null_model(matrix, positions=None, model="uniform", noisy=False):
    n,m = matrix.shape
    positions_supplied = True
    if positions is None:
        positions = range(n)
        positions_supplied = False
        
    contigs = np.array(positions_to_contigs(positions))
    
    def is_inter(i,j):
        return contigs[i] != contigs[j]
    def is_intra(i,j):
        return not is_inter(i,j)
    
    diagonal = np.diag(matrix)    
    
    if model == "uniform":
        if positions_supplied:
            trans_contacts = np.array([matrix[i,j] for i,j in itertools.product(range(n),range(m)) if is_inter(i,j)])
            mean_trans_contacts = np.average(trans_contacts)
        else:
            mean_trans_contacts = np.average(matrix) - diagonal/len(diagonal)
            
        N = np.random.poisson(lam=mean_trans_contacts,size=(n,m))
        np.fill_diagonal(N,diagonal)
        
    elif model == "distance":
        distances = distance_diagonal_law(matrix)
        N = np.array([[distances[min(abs(i-j),n)] for i in range(n)] for j in range(n)])
    if noisy:
        return noise(N)
    else:
        return N
