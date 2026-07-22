#!/usr/bin/env python3
# pushout_finite_construction.py
# Finite pushout construction for A_log = M2, B = M6, C = M2 with α embedding top-left block.

import numpy as np
from numpy.linalg import svd, lstsq, matrix_rank

# Basic utilities
def vec(mat):
    # column-stack flatten
    return mat.reshape(-1, order='F')  # Fortran order (column-major)

def mat_from_vec(v, rows, cols):
    return v.reshape((rows, cols), order='F')

def kron(a, b):
    return np.kron(a, b)

# Parameters
d = 2          # logical dimension
N = 6          # boundary dimension
b = 2          # bulk dimension (same as d in this toy)
dim_B = N * N
dim_C = b * b
dim_A = d * d

# Basis: matrix units E_{ij} for M_d
def matrix_units(d):
    mats = []
    for i in range(d):
        for j in range(d):
            M = np.zeros((d, d), dtype=complex)
            M[i, j] = 1.0
            mats.append(M)
    return mats

E_A = matrix_units(d)  # list of d^2 basis matrices

# Define isometry V: embed logical 2-dim into first two coords of 6-dim
V = np.zeros((N, d), dtype=complex)
V[0, 0] = 1.0
V[1, 1] = 1.0
# check isometry
assert np.allclose(V.conj().T @ V, np.eye(d))

# Define alpha: A -> B by conjugation V O V^†, embedded into M6
def alpha(O):
    # produce N x N matrix (top-left block = O, rest zeros)
    B = np.zeros((N, N), dtype=complex)
    B[:d, :d] = O
    return B

# Define beta: A -> C (identity copy into M2)
def beta(O):
    return O.copy()

# Build relation vectors for all basis elements of A: r = (vec(alpha(E)), -vec(beta(E)))
R_cols = []
for E in E_A:
    vB = vec(alpha(E))            # dim_B vector
    vC = vec(beta(E))             # dim_C vector
    r = np.concatenate([vB, -vC]) # dim_B + dim_C vector
    R_cols.append(r.reshape(-1,1))

R = np.hstack(R_cols)  # shape (dim_B + dim_C, dim_A)

# Compute rank and nullspace complement
U, S, Vh = svd(R, full_matrices=True)
tol = 1e-12
rankR = (S > tol).sum()
print("Dimensions: dim_B={}, dim_C={}, dim_A={}, rank(R)={}".format(dim_B, dim_C, dim_A, rankR))

# Nullspace of R^T gives quotient basis (vectors in V_space orthogonal to all rows of R^T)
# Equivalent: compute nullspace of R^T: solve R^T x = 0
# Using SVD of R^T:
Ut, St, Vht = svd(R.T)
rankRt = (St > tol).sum()
null_dim = (R.shape[0] - rankR)  # alternative: dim(V_space) - rank(R)
print("Expected quotient dimension =", R.shape[0] - rankR)
# Nullspace basis for R^T is columns of Vht.T[:, rankRt:]
nullspace = Vht.T[:, rankRt:]
# The columns of nullspace are basis vectors for quotient space (in V_space)
Q_basis = nullspace  # shape (V_space_dim, q_dim)
q_dim = Q_basis.shape[1]
print("Quotient dimension q_dim =", q_dim)

# Build projection from V_space to quotient coordinates: for a vector v in V_space, coords = Q_coord solving Q_basis @ coords = v (least squares)
# Since columns of Q_basis are orthonormal (from SVD), projection is simply coords = Q_basis.conj().T @ v
# However Vht from SVD yields orthonormal columns in Vht.T, so Q_basis columns are orthonormal.

# Helper: project a V_space vector to quotient coords
def project_to_quotient(v):
    # returns coords in C^{q_dim}
    return Q_basis.conj().T @ v

# Helper: reconstruct representative vector in V_space from quotient coords
def representative_from_coords(coords):
    return Q_basis @ coords

# Build a list of representative basis vectors in quotient: take canonical images of basis elements of B⊕C: e_k
V_space_dim = dim_B + dim_C
# Unit vectors for V_space: columns of identity
I = np.eye(V_space_dim, dtype=complex)
# Build quotient images of the canonical basis of B and C
basis_coords = []
for k in range(V_space_dim):
    v = I[:, k]
    coords = project_to_quotient(v)
    basis_coords.append(coords)

# For multiplication we need a set of representative V_space vectors corresponding to quotient basis vectors.
# Choose q_dim linearly independent representatives: columns of Q_basis are a basis in V_space for quotient subspace.
rep_vectors = [Q_basis[:, i] for i in range(q_dim)]

# Build multiplication on quotient basis by multiplying representative pairs and projecting back
# We will produce left-multiplication matrices L_i corresponding to each quotient basis vector i
# First build mapping from rep index to representative vector
rep_matrix = np.column_stack(rep_vectors)  # V_space_dim x q_dim

# Multiplication in V_space: multiply (b1,c1) and (b2,c2) componentwise for algebras B and C
# For general v in V_space, interpret as pair (vecB, vecC)
def multiply_Vspace(u, v):
    # u, v are vectors length V_space_dim
    vecB_u = u[:dim_B]
    vecC_u = u[dim_B:]
    vecB_v = v[:dim_B]
    vecC_v = v[dim_B:]
    # convert vec back to matrices for multiplication
    B_u = mat_from_vec(vecB_u, N, N)
    C_u = mat_from_vec(vecC_u, b, b)
    B_v = mat_from_vec(vecB_v, N, N)
    C_v = mat_from_vec(vecC_v, b, b)
    B_prod = B_u @ B_v
    C_prod = C_u @ C_v
    return np.concatenate([vec(B_prod), vec(C_prod)])

# Precompute left-multiplication matrices L so that L_i * coords_vector = coords of product (rep_i * element)
L_mats = []
for i in range(q_dim):
    rep_i = rep_vectors[i]
    # For each quotient basis vector j (represented by rep_j), compute product rep_i * rep_j, project to quotient coords
    cols = []
    for j in range(q_dim):
        rep_j = rep_vectors[j]
        prod = multiply_Vspace(rep_i, rep_j)
        coords_prod = project_to_quotient(prod)
        cols.append(coords_prod)
    L = np.column_stack(cols)  # q_dim x q_dim matrix: columns are coords of rep_i * rep_j
    L_mats.append(L)

print("Constructed {} left-multiplication matrices of size {}x{}".format(len(L_mats), q_dim, q_dim))

# Quick sanity: check associativity on a few random triples by checking (L_i L_j) vs product via multiplication
def multiply_coords(coords_u, coords_v):
    # reconstruct V_space representatives, multiply, then project
    u = representative_from_coords(coords_u)
    v = representative_from_coords(coords_v)
    prod = multiply_Vspace(u, v)
    return project_to_quotient(prod)

# Sample random combination check
import random
i, j, k = 0, 1, 2 if q_dim>2 else (0, 0, 0)
coords_i = np.eye(q_dim)[:, i]
coords_j = np.eye(q_dim)[:, j]
coords_k = np.eye(q_dim)[:, k]
left = multiply_coords(multiply_coords(coords_i, coords_j), coords_k)
right = multiply_coords(coords_i, multiply_coords(coords_j, coords_k))
print("Associativity check norm(left-right) =", np.linalg.norm(left - right))

# Optionally produce matrix representation of algebra by left regular representation:
# For an element with coords x (q_dim vector), left action on algebra coords is M_x = sum_i x_i * L_mats[i]
def left_action_matrix(coords_x):
    M = np.zeros((q_dim, q_dim), dtype=complex)
    for idx in range(q_dim):
        M += coords_x[idx] * L_mats[idx]
    return M

# Example: left action of first basis element
coords_basis0 = np.eye(q_dim)[:,0]
M0 = left_action_matrix(coords_basis0)
print("Left action matrix for basis element 0 (shape):", M0.shape)

# Print summary
print("\n" + "="*60)
print("PUSHOUT ALGEBRA CONSTRUCTION SUMMARY")
print("="*60)
print("Source algebras:")
print(f"  A_log: M_{d} (dimension {dim_A})")
print(f"  B: M_{N} (dimension {dim_B})")
print(f"  C: M_{b} (dimension {dim_C})")
print(f"Vector space: B ⊕ C (dimension {V_space_dim})")
print(f"Relation space rank: {rankR}")
print(f"Quotient algebra dimension: {q_dim}")
print(f"Left-multiplication matrices: {len(L_mats)} of size {q_dim}×{q_dim}")
print("="*60)

# Save results or inspect eigenstructure if desired
# np.savez('pushout_data.npz', L_mats=L_mats, Q_basis=Q_basis)
