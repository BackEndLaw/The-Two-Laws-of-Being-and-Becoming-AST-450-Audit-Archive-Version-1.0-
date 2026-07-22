# Huckel pi-Electron Stabilization Energy of Benzene Relative to Hexatriene

## A matrix-algebra derivation for $\Delta E_\pi = 1.0121\,\beta$

### Abstract
Using closed-form eigenvalue formulae for the path graph $P_6$ (1,3,5-hexatriene) and cycle graph $C_6$ (benzene), we derive the Huckel pi-electron energies by diagonalizing the corresponding adjacency matrices. The energy difference is
\[
\Delta E_\pi = E_\pi(C_6)-E_\pi(P_6)=1.012082\,\beta\approx 1.0121\,\beta.
\]
With the conventional Huckel sign $\beta<0$, this is a net stabilization of benzene. Taking $\beta\approx -75\,\text{kJ mol}^{-1}$ gives $\Delta E_\pi\approx -76\,\text{kJ mol}^{-1}$.

## 1) Huckel Hamiltonian and graph representation
In the $p_z$ AO basis,
\[
H_G = \alpha I + \beta A_G,
\]
where $A_G$ is the (0,1) adjacency matrix of the carbon skeleton. Because $\alpha I$ shifts all MO energies uniformly, relative energies are independent of $\alpha$.

Define reduced eigenvalues $x_k$ by
\[
A_G c_k = x_k c_k,\qquad \varepsilon_k = \alpha + \beta x_k.
\]
For 6 pi-electrons, the total pi-energy is
\[
E_\pi = 2\sum_{k\in \text{occ}} \varepsilon_k.
\]

## 2) Adjacency matrices
### Path graph $P_6$ (hexatriene)
\[
A(P_6)=
\begin{bmatrix}
0&1&0&0&0&0\\
1&0&1&0&0&0\\
0&1&0&1&0&0\\
0&0&1&0&1&0\\
0&0&0&1&0&1\\
0&0&0&0&1&0
\end{bmatrix}.
\]

### Cycle graph $C_6$ (benzene)
\[
A(C_6)=
\begin{bmatrix}
0&1&0&0&0&1\\
1&0&1&0&0&0\\
0&1&0&1&0&0\\
0&0&1&0&1&0\\
0&0&0&1&0&1\\
1&0&0&0&1&0
\end{bmatrix}
= A(P_6)+\Delta A,
\]
with nonzero perturbation entries $\Delta A_{16}=\Delta A_{61}=1$.

## 3) Analytic eigenvalues
### 3.1 Open chain $P_N$
For the tridiagonal Jacobi matrix,
\[
x_k(P_N)=2\cos\!\left(\frac{k\pi}{N+1}\right),\quad k=1,\dots,N.
\]
For $N=6$:
\[
\begin{aligned}
x_1&=2\cos(\pi/7)=1.801938,\\
x_2&=2\cos(2\pi/7)=1.246980,\\
x_3&=2\cos(3\pi/7)=0.445042,
\end{aligned}
\]
and $x_4,x_5,x_6$ are the corresponding negatives.

### 3.2 Ring $C_N$
For the circulant cycle adjacency,
\[
x_k(C_N)=2\cos\!\left(\frac{2\pi k}{N}\right),\quad k=0,\dots,N-1.
\]
For $N=6$:
\[
\{x_k\} = \{2,1,1,-1,-1,-2\}.
\]

## 4) Total pi-electron energies
### 4.1 Hexatriene $P_6$
Occupied reduced eigenvalues are $x_1,x_2,x_3$:
\[
\begin{aligned}
E_\pi(P_6)
&=2\big[(\alpha+\beta x_1)+(\alpha+\beta x_2)+(\alpha+\beta x_3)\big]\\
&=6\alpha+2\beta(x_1+x_2+x_3)\\
&=6\alpha+2\beta(1.801938+1.246980+0.445042)\\
&=6\alpha+6.987918\,\beta.
\end{aligned}
\]

### 4.2 Benzene $C_6$
Occupied reduced eigenvalues are $2,1,1$:
\[
\begin{aligned}
E_\pi(C_6)
&=2\big[(\alpha+2\beta)+(\alpha+\beta)+(\alpha+\beta)\big]\\
&=6\alpha+8.000000\,\beta.
\end{aligned}
\]

## 5) Aromatic stabilization from ring closure
\[
\begin{aligned}
\Delta E_\pi
&=E_\pi(C_6)-E_\pi(P_6)\\
&=(6\alpha+8\beta)-(6\alpha+6.987918\beta)\\
&=1.012082\,\beta\approx 1.0121\,\beta.
\end{aligned}
\]
Equivalent trigonometric form:
\[
\Delta E_\pi=
\left[8-4\left(\cos\frac{\pi}{7}+\cos\frac{2\pi}{7}+\cos\frac{3\pi}{7}\right)\right]\beta.
\]
Using
\[
\cos\frac{\pi}{7}=0.9009689,\quad
\cos\frac{2\pi}{7}=0.6234898,\quad
\cos\frac{3\pi}{7}=0.2225209,
\]
we get
\[
\Delta E_\pi = [8-4(1.7469796)]\beta = 1.0120816\,\beta.
\]

## 6) Interpretation
1. Topological change: adding edge $(1,6)$ converts open boundary ($P_6$) to periodic boundary ($C_6$), changing the operator spectrum.
2. Energetic consequence: with $\beta<0$, positive $\Delta E_\pi/\beta$ means negative physical energy change, i.e., stabilization of the ring.
3. Delocalization signature: bond-order alternation in $P_6$ is replaced by uniform bond orders ($2/3$) in $C_6$ under Huckel filling.

## 7) Final result
\[
\boxed{\Delta E_\pi = E_\pi(C_6)-E_\pi(P_6)=1.0121\,\beta}
\]
and for $\beta\approx -75\,\text{kJ mol}^{-1}$,
\[
\Delta E_\pi\approx -76\,\text{kJ mol}^{-1}.
\]

---
This version uses one consistent Huckel convention, explicit occupancy counting, and corrected subtraction in the trigonometric form.

## Appendix (Short): MO coefficients, densities, and bond orders
For a closed-shell pi system with occupied MOs $k\in\text{occ}$:
\[
\rho_r = 2\sum_{k\in\text{occ}} c_{r,k}^2,
\qquad
p_{rs} = 2\sum_{k\in\text{occ}} c_{r,k}c_{s,k}.
\]

For $P_6$, the analytic coefficients are
\[
c_{r,k}(P_6)=\sqrt{\frac{2}{7}}\sin\!\left(\frac{rk\pi}{7}\right),\quad r,k=1,\dots,6.
\]
For $C_6$, coefficients may be written in DFT form
\[
c_{r,k}(C_6)=\frac{1}{\sqrt{6}}\exp\!\left(\frac{2\pi i rk}{6}\right),
\]
or as equivalent real cosine/sine combinations for degenerate pairs.

Using the occupied levels stated above, key Huckel results are:
1. $P_6$ bond orders (nearest-neighbor): $p_{12}=p_{56}\approx0.8711$, $p_{23}=p_{45}\approx0.4834$, $p_{34}\approx0.7849$.
2. $C_6$ bond orders (all six bonds): $p_{rs}=2/3\approx0.6667$.
3. Site densities in both systems: $\rho_r=1$ for each carbon ($r=1,\dots,6$).

This compactly captures the transition from bond alternation in $P_6$ to uniform delocalization in $C_6$.
