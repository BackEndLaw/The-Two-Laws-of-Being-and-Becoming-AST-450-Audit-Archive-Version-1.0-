"""
Pushout Algebra Construction: P = (B ⊕ C) / R

Constructs a quotient algebra via pushout diagram where:
- B and C are algebras with known basis representations
- alpha: A -> B, beta: A -> C are homomorphisms
- Relations R embed the kernel of the diagram
- P is the resulting quotient algebra in B ⊕ C / R

Author: Algebraic Computation
Date: 2026
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class AlgebraRepresentation:
    """Represents an algebra via its multiplication table or basis matrices."""
    basis_size: int
    basis_matrices: Optional[List[np.ndarray]] = None
    multiplication_table: Optional[np.ndarray] = None


class PushoutAlgebra:
    """
    Constructs and represents a pushout algebra P = (B ⊕ C) / R.
    
    The construction proceeds as follows:
    1. Form vector-space direct sum of B and C
    2. Compute relation space R from homomorphisms alpha, beta
    3. Find quotient basis via SVD (nullspace complement)
    4. Define multiplication in quotient space
    5. Produce regular representation matrices
    """
    
    def __init__(self, dim_B: int, dim_C: int, tol: float = 1e-12):
        """
        Initialize pushout algebra construction.
        
        Args:
            dim_B: Dimension of algebra B
            dim_C: Dimension of algebra C
            tol: Numerical tolerance for rank detection
        """
        self.dim_B = dim_B
        self.dim_C = dim_C
        self.V_space_dim = dim_B + dim_C
        self.tol = tol
        
        self.R_mat = None  # Relation matrix
        self.rank = None   # Rank of relation space
        self.quotient_basis = None  # Basis vectors for quotient
        self.quotient_dim = None    # Dimension of quotient algebra
        self.left_mult_matrices = {}  # L_x for basis elements
        
    def vec(self, matrix: np.ndarray) -> np.ndarray:
        """
        Vectorize a matrix by stacking columns (column-major order).
        
        Args:
            matrix: Input matrix
            
        Returns:
            1D array (vec of matrix)
        """
        return matrix.flatten(order='F')
    
    def unvec(self, vector: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
        """
        Reconstruct matrix from vectorized form.
        
        Args:
            vector: 1D vectorized array
            shape: Target matrix shape (rows, cols)
            
        Returns:
            Reconstructed matrix
        """
        return vector.reshape(shape, order='F')
    
    def build_relation_space(self, 
                            basis_A: List[np.ndarray],
                            alpha_images: List[np.ndarray],
                            beta_images: List[np.ndarray]) -> np.ndarray:
        """
        Construct relation matrix from homomorphisms alpha and beta.
        
        For each basis element E of A:
        - Compute vec(alpha(E)) in C^dim_B
        - Compute vec(beta(E)) in C^dim_C
        - Form relation vector: [vec(alpha(E)), -vec(beta(E))]
        
        Args:
            basis_A: List of basis matrices for algebra A
            alpha_images: List of images alpha(E) for each basis element
            beta_images: List of images beta(E) for each basis element
            
        Returns:
            Relation matrix R (V_space_dim x len(basis_A))
        """
        relation_vectors = []
        
        for alpha_E, beta_E in zip(alpha_images, beta_images):
            vec_alphaE = self.vec(alpha_E)  # dim_B elements
            vec_betaE = self.vec(beta_E)     # dim_C elements
            
            # Stack to form relation in B ⊕ C
            r_k = np.concatenate([vec_alphaE, -vec_betaE])
            relation_vectors.append(r_k)
        
        # Stack all relation vectors as columns
        self.R_mat = np.column_stack(relation_vectors)
        return self.R_mat
    
    def compute_quotient_basis(self) -> np.ndarray:
        """
        Find orthonormal basis for quotient space via SVD.
        
        The quotient space is the nullspace of R_mat^T, i.e.,
        vectors v such that R_mat^T @ v = 0.
        
        Using SVD: R_mat = U @ S @ Vh
        - Nullspace of R_mat^T corresponds to singular vectors
          with zero singular values (or near-zero for rank)
        
        Returns:
            Quotient basis matrix (V_space_dim x quotient_dim)
        """
        if self.R_mat is None:
            raise ValueError("Must call build_relation_space first")
        
        # SVD for numerical stability
        U, S, Vh = np.linalg.svd(self.R_mat, full_matrices=True)
        
        # Determine rank
        self.rank = (S > self.tol).sum()
        self.quotient_dim = self.V_space_dim - self.rank
        
        # Nullspace basis: singular vectors corresponding to zero singular values
        # These are the rows of Vh with index >= rank
        nullspace_basis = Vh[self.rank:, :].conj().T
        
        self.quotient_basis = nullspace_basis
        return nullspace_basis
    
    def project_to_quotient(self, vector: np.ndarray) -> np.ndarray:
        """
        Project a vector from V_space onto the quotient basis.
        
        Args:
            vector: Vector in R^V_space_dim
            
        Returns:
            Coordinates with respect to quotient basis
        """
        if self.quotient_basis is None:
            raise ValueError("Must call compute_quotient_basis first")
        
        # Project: solve quotient_basis @ coords = vector (least-squares)
        coords, _, _, _ = np.linalg.lstsq(self.quotient_basis, vector, rcond=None)
        return coords
    
    def define_multiplication(self,
                             B_mult_table: np.ndarray,
                             C_mult_table: np.ndarray) -> None:
        """
        Define multiplication in the quotient algebra.
        
        For each pair of quotient basis vectors q_i, q_j:
        1. Lift to representatives in B ⊕ C
        2. Multiply representatives
        3. Project result back onto quotient basis
        
        Args:
            B_mult_table: Multiplication table for B (dim_B x dim_B x dim_B)
            C_mult_table: Multiplication table for C (dim_C x dim_C x dim_C)
        """
        if self.quotient_basis is None:
            raise ValueError("Must call compute_quotient_basis first")
        
        self.multiplication_table = np.zeros((self.quotient_dim, 
                                              self.quotient_dim, 
                                              self.quotient_dim))
        
        for i in range(self.quotient_dim):
            for j in range(self.quotient_dim):
                # Representatives in B ⊕ C
                rep_i = self.quotient_basis[:, i]
                rep_j = self.quotient_basis[:, j]
                
                # Split into B and C parts
                b_i = rep_i[:self.dim_B]
                c_i = rep_i[self.dim_B:]
                b_j = rep_j[:self.dim_B]
                c_j = rep_j[self.dim_B:]
                
                # Multiply in B and C using structure constants
                b_prod = self._multiply_by_structure(b_i, b_j, B_mult_table, self.dim_B)
                c_prod = self._multiply_by_structure(c_i, c_j, C_mult_table, self.dim_C)
                
                # Form product in B ⊕ C
                prod_in_sum = np.concatenate([b_prod, c_prod])
                
                # Project onto quotient basis
                coords = self.project_to_quotient(prod_in_sum)
                self.multiplication_table[i, j, :] = coords
    
    def _multiply_by_structure(self, 
                               v1: np.ndarray, 
                               v2: np.ndarray,
                               mult_table: np.ndarray,
                               dim: int) -> np.ndarray:
        """
        Multiply two elements represented in structure constant basis.
        
        Args:
            v1, v2: Coefficient vectors
            mult_table: Multiplication table (dim x dim x dim)
            dim: Dimension of algebra
            
        Returns:
            Product vector
        """
        product = np.zeros(dim)
        for i in range(dim):
            for j in range(dim):
                for k in range(dim):
                    product[k] += v1[i] * v2[j] * mult_table[i, j, k]
        return product
    
    def assemble_regular_representation(self) -> List[np.ndarray]:
        """
        Construct left-multiplication matrices L_x for basis elements.
        
        For each quotient basis element x, L_x is the matrix such that
        (L_x @ v) gives coordinates of x * v in the quotient basis.
        
        Returns:
            List of left-multiplication matrices
        """
        if self.multiplication_table is None:
            raise ValueError("Must call define_multiplication first")
        
        self.left_mult_matrices = []
        
        for i in range(self.quotient_dim):
            L_i = np.zeros((self.quotient_dim, self.quotient_dim))
            for j in range(self.quotient_dim):
                # i * j has coordinates given by multiplication_table[i, j, :]
                L_i[:, j] = self.multiplication_table[i, j, :]
            self.left_mult_matrices.append(L_i)
        
        return self.left_mult_matrices
    
    def summary(self) -> dict:
        """Return summary of pushout algebra construction."""
        return {
            'dim_B': self.dim_B,
            'dim_C': self.dim_C,
            'V_space_dim': self.V_space_dim,
            'relation_rank': self.rank,
            'quotient_dimension': self.quotient_dim,
            'num_left_mult_matrices': len(self.left_mult_matrices) if self.left_mult_matrices else 0,
        }


# ============================================================================
# Example Usage: Pushout of two copies of 2×2 matrices over their common subalgebra
# ============================================================================

def example_matrix_algebra_pushout():
    """
    Example: Construct pushout of Mat(2,2) algebras.
    
    This demonstrates the full pipeline:
    - Define algebras B, C (both Mat(2,2))
    - Define shared subalgebra A (diagonal matrices)
    - Construct embeddings alpha: A -> B, beta: A -> C
    - Build quotient algebra
    """
    
    # Initialize
    dim_B = 4  # Mat(2,2) is 4-dimensional
    dim_C = 4
    pushout = PushoutAlgebra(dim_B, dim_C)
    
    # Example: basis for A_log (logarithmic algebra, small basis)
    # Use 2 generators for diagonal structure
    basis_A = [
        np.array([[1, 0], [0, 0]]),  # E_11
        np.array([[0, 0], [0, 1]]),  # E_22
    ]
    
    # Embeddings alpha, beta: A -> Mat(2,2)
    # For simplicity, use identity embedding
    alpha_images = [
        np.array([[1, 0], [0, 0]]),  # α(E_11)
        np.array([[0, 0], [0, 1]]),  # α(E_22)
    ]
    beta_images = [
        np.array([[1, 0], [0, 0]]),  # β(E_11)
        np.array([[0, 0], [0, 1]]),  # β(E_22)
    ]
    
    # Build relation space
    R_mat = pushout.build_relation_space(basis_A, alpha_images, beta_images)
    print(f"Relation matrix shape: {R_mat.shape}")
    print(f"Relation matrix rank: {np.linalg.matrix_rank(R_mat)}")
    
    # Compute quotient basis
    quotient_basis = pushout.compute_quotient_basis()
    print(f"Quotient basis shape: {quotient_basis.shape}")
    print(f"Quotient algebra dimension: {pushout.quotient_dim}")
    
    # For full example, would define multiplication tables for B, C
    # and call define_multiplication() and assemble_regular_representation()
    
    print("\nPushout Algebra Summary:")
    for key, value in pushout.summary().items():
        print(f"  {key}: {value}")
    
    return pushout


if __name__ == "__main__":
    pushout = example_matrix_algebra_pushout()
