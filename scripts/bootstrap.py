#!/usr/bin/env python2
"""
PyCFTBoot is an interface for the numerical bootstrap in arbitrary dimension,
a field that was initiated in 2008 by Rattazzi, Rychkov, Tonni and Vichi in
arXiv:0807.0004. Starting from the analytic structure of conformal blocks, the
code formulates semidefinite programs without any proprietary software. The
actual optimization step must be performed by David Simmons-Duffin's program
SDPB available at https://github.com/davidsd/sdpb.

PyCFTBoot may be used to find bounds on OPE coefficients and allowed regions in
the space of scaling dimensions for various CFT operators. All operators used in
the explicit correlators must be scalars, but they may have different scaling
dimensions and transform in arbitrary representations of a global symmetry.
"""
from __future__ import print_function
import xml.dom.minidom
import numpy.polynomial
import mpmath
import re
import subprocess

# Use regular sympy sparingly because it is slow
# Every time we explicitly use it, we should consider implementing such a line in C++
from symengine import *
from symengine.lib.symengine_wrapper import *
import sympy

# Set MAX_THREADS to 4 by default unless env variable $PBS_NP is set
import os
MAX_THREADS = os.getenv('PBS_NP', 4)

if have_mpfr == False:
    print("Symengine must be compiled with MPFR support")
    quit(1)

cutoff = 0
prec = 660
mpmath.mp.dps = int((3.0 / 10.0) * prec)

rho_cross = 3 - 2 * mpmath.sqrt(2)
r_cross = eval_mpfr(3 - 2 * sqrt(2), prec)

ell = symbols('ell')
delta  = symbols('delta')
delta_ext = symbols('delta_ext')
aux = symbols('aux')

def dump_table_contents(block_table, name):
    dump_file = open(name, 'w')

    dump_file.write("self.dim = " + block_table.dim.__str__() + "\n")
    dump_file.write("self.k_max = " + block_table.k_max.__str__() + "\n")
    dump_file.write("self.l_max = " + block_table.l_max.__str__() + "\n")
    dump_file.write("self.m_max = " + block_table.m_max.__str__() + "\n")
    dump_file.write("self.n_max = " + block_table.n_max.__str__() + "\n")
    dump_file.write("self.delta_12 = " + block_table.delta_12.__str__() + "\n")
    dump_file.write("self.delta_34 = " + block_table.delta_34.__str__() + "\n")
    dump_file.write("self.odd_spins = " + block_table.odd_spins.__str__() + "\n")
    dump_file.write("self.m_order = " + block_table.m_order.__str__() + "\n")
    dump_file.write("self.n_order = " + block_table.n_order.__str__() + "\n")
    dump_file.write("self.table = []\n")

    for l in range(0, len(block_table.table)):
        dump_file.write("derivatives = []\n")
        for i in range(0, len(block_table.table[0].vector)):
            poly_string = block_table.table[l].vector[i].__str__()
            poly_string = re.sub("([0-9]+\.[0-9]+e?-?[0-9]+)", r"eval_mpfr(\1, prec)", poly_string)
            dump_file.write("derivatives.append(" + poly_string + ")\n")
        dump_file.write("self.table.append(PolynomialVector(derivatives, " + block_table.table[l].label.__str__() + ", " + block_table.table[l].poles.__str__() + "))\n")

    dump_file.close()

def unitarity_bound(dim, spin):
    if spin == 0:
        return sympy.Rational(dim, 2) - 1
    else:
        return dim + spin - 2

def omit_all(poles, special_poles, var):
    expression = 1
    for p in poles:
        if not p in special_poles:
            expression *= (var - p)
    return expression

def delta_pole(nu, k, l, series):
    if nu % 1 == 0:
        nu = int(nu)

    if series == 1:
        pole = 1 - l - k
    elif series == 2:
        pole = 1 + nu - k
        if nu % 1 == 0:
            pole += aux
    else:
        pole = 1 + l + 2 * nu - k
        if nu % 1 == 0:
            pole += 2 * aux

    if nu % 1 == 0:
        return pole
    else:
        return eval_mpfr(pole, prec)

class LeadingBlockVector:
    def __init__(self, dim, l, m_max, n_max, delta_12, delta_34):
        self.spin = l
        self.m_max = m_max
        self.n_max = n_max
        self.chunks = []

        r = symbols('r')
        eta = symbols('eta')
        nu = sympy.Rational(dim, 2) - 1
        derivative_order = m_max + 2 * n_max

        # With only a derivatives, we never need eta derivatives
        off_diag_order = derivative_order
        if n_max == 0:
            off_diag_order = 0

        # We cache derivatives as we go
        # This is because csympy can only compute them one at a time, but it's faster anyway
        old_expression = self.leading_block(nu, r, eta, l, delta_12, delta_34)

        for n in range(0, off_diag_order + 1):
            chunk = []
            for m in range(0, derivative_order - n + 1):
                if n == 0 and m == 0:
                    expression = old_expression
                elif m == 0:
                    old_expression = old_expression.diff(eta)
                    expression = old_expression
                else:
                    expression = expression.diff(r)

                chunk.append(expression.subs({r : r_cross, eta : 1}))
            self.chunks.append(DenseMatrix(len(chunk), 1, chunk))

    def leading_block(self, nu, r, eta, l, delta_12, delta_34):
        if self.n_max == 0:
            ret = 1
        elif nu == 0:
            ret = sympy.chebyshevt(l, eta)
        else:
            ret = factorial(l) * sympy.gegenbauer(l, nu, eta) / sympy.rf(2 * nu, l)

        one = eval_mpfr(1, prec)
        two = eval_mpfr(2, prec)

        # Time saving special case
        if delta_12 == delta_34:
            return ((-1) ** l) * ret / (((1 - r ** 2) ** nu) * sqrt((1 + r ** 2) ** 2 - 4 * (r * eta) ** 2))
        else:
            return ((-1) ** l) * ret / (((1 - r ** 2) ** nu) * ((1 + r ** 2 + 2 * r * eta) ** ((one + delta_12 - delta_34) / two)) * ((1 + r ** 2 - 2 * r * eta) ** ((one - delta_12 + delta_34) / two)))

class MeromorphicBlockVector:
    def __init__(self, leading_block):
        # A chunk is a set of r derivatives for one eta derivative
        # The matrix that should multiply a chunk is just R restricted to the right length
        self.chunks = []

        for j in range(0, len(leading_block.chunks)):
            rows = leading_block.chunks[j].nrows()
            self.chunks.append(DenseMatrix(rows, 1, [0] * rows))
            for n in range(0, rows):
                self.chunks[j].set(n, 0, leading_block.chunks[j].get(n, 0))

class ConformalBlockVector:
    def __init__(self, dim, l, delta_12, delta_34, derivative_order, kept_pole_order, s_matrix, leading_block, pol_list, res_list):
        self.large_poles = []
        self.small_poles = []
        self.chunks = []

        nu = sympy.Rational(dim, 2) - 1
        old_list = MeromorphicBlockVector(leading_block)
        for k in range(0, len(pol_list)):
            pole = delta_pole(nu, pol_list[k][1], l, pol_list[k][3])
            if "subs" in dir(pole):
                pole = pole.subs(aux, 0)

            if abs(float(res_list[k].chunks[0].get(0, 0))) < cutoff:
                self.small_poles.append(pole)
            else:
                self.large_poles.append(pole)

        matrix = []
        if self.small_poles != []:
            for i in range(0, len(self.large_poles) // 2):
                for j in range(0, len(self.large_poles)):
                    matrix.append(1 / ((cutoff + unitarity_bound(dim, l) - self.large_poles[j]) ** (i + 1)))
            for i in range(0, len(self.large_poles) - (len(self.large_poles) // 2)):
                for j in range(0, len(self.large_poles)):
                    matrix.append(1 / (((1 / cutoff) - self.large_poles[j]) ** (i + 1)))
            matrix = DenseMatrix(len(self.large_poles), len(self.large_poles), matrix)
            matrix = matrix.inv()

        for j in range(0, len(leading_block.chunks)):
            self.chunks.append(leading_block.chunks[j])
            for p in self.large_poles:
                self.chunks[j] = self.chunks[j].mul_scalar(delta - p)

        for k in range(0, len(pol_list)):
            pole = delta_pole(nu, pol_list[k][1], l, pol_list[k][3])
            if "subs"in dir(pole):
                pole = pole.subs(aux, 0)

            if pole in self.large_poles:
                for j in range(0, len(self.chunks)):
                    self.chunks[j] = self.chunks[j].add_matrix(res_list[k].chunks[j].mul_scalar(omit_all(self.large_poles, [pole], delta)))
            else:
                vector = []
                for i in range(0, len(self.large_poles) // 2):
                    vector.append(1 / ((unitarity_bound(dim, l) - pole) ** (i + 1)))
                for i in range(0, len(self.large_poles) - (len(self.large_poles) // 2)):
                    vector.append(1 / (((1 / cutoff) - pole) ** (i + 1)))
                vector = DenseMatrix(len(self.large_poles), 1, vector)
                vector = matrix.mul_matrix(vector)
                for i in range(0, len(self.large_poles)):
                    for j in range(0, len(self.chunks)):
                        self.chunks[j] = self.chunks[j].add_matrix(res_list[k].chunks[j].mul_scalar(vector.get(i, 0) * omit_all(self.large_poles, [self.large_poles[i]], delta)))

        for j in range(0, len(self.chunks)):
            s_sub = s_matrix.submatrix(0, derivative_order - j, 0, derivative_order - j)
            self.chunks[j] = s_sub.mul_matrix(self.chunks[j])

class PolynomialVector:
    """
    The main class for vectors on which the functionals being found by SDPB may act.

    Attributes
    ----------
    vector: A list of the components, expected to be polynomials in `delta`. The
            number of components is dictated by the number of derivatives kept in
            the search space.
    label:  A two element list where the first element is the spin and the second
            is a user-defined label for the representation of some global symmetry
            (or 0 if none have been set yet).
    poles:  A list of roots of the common denominator shared by all entries in
            `vector`. This allows one to go back to the original rational functions
            instead of the more convenient polynomials.
    """
    def __init__(self, derivatives, spin_irrep, poles):
        if type(spin_irrep) == type(1):
            spin_irrep = [spin_irrep, 0]
        self.vector = derivatives
        self.label = spin_irrep
        self.poles = poles

class ConformalBlockTableSeed:
    """
    A class which calculates tables of conformal block derivatives from scratch.
    Usually, it will not be necessary for the user to call it. Instead,
    `ConformalBlockTable` calls it automatically for `m_max = 3` and `n_max = 0`.
    For people wanting to call it with different values of `m_max` and `n_max`,
    the parameters and attributes are the same as those of `ConformalBlockTable`.
    It also supports the `dump` method.
    """
    def __init__(self, dim, k_max, l_max, m_max, n_max, delta_12 = 0, delta_34 = 0, odd_spins = False, name = None):
        self.dim = dim
        self.k_max = k_max
        self.l_max = l_max
        self.m_max = m_max
        self.n_max = n_max
        self.delta_12 = delta_12
        self.delta_34 = delta_34
        self.odd_spins = odd_spins
        self.m_order = []
        self.n_order = []
        self.table = []

        if odd_spins:
            step = 1
        else:
            step = 2

        if name != None:
            dump_file = open(name, 'r')
            command = dump_file.read()
            exec(command)
            return

        derivative_order = m_max + 2 * n_max
        nu = sympy.Rational(dim, 2) - 1

        # The matrix for how derivatives are affected when one multiplies by r
        r_powers = []
        identity = [0] * ((derivative_order + 1) ** 2)
        lower_band = [0] * ((derivative_order + 1) ** 2)

        for i in range(0, derivative_order + 1):
            identity[i * (derivative_order + 1) + i] = 1
        for i in range(1, derivative_order + 1):
            lower_band[i * (derivative_order + 1) + i - 1] = i

        identity = DenseMatrix(derivative_order + 1, derivative_order + 1, identity)
        lower_band = DenseMatrix(derivative_order + 1, derivative_order + 1, lower_band)
        r_matrix = identity.mul_scalar(r_cross).add_matrix(lower_band)
        r_powers.append(identity)
        r_powers.append(r_matrix)

        conformal_blocks = []
        leading_blocks = []
        pol_list = []
        res_list = []
        pow_list = []
        den_list = []
        new_res_list = []
        old_den_list = []

        # Find out which residues we will ever need to include
        for l in range(0, l_max + k_max + 1):
            lb = LeadingBlockVector(dim, l, m_max, n_max, delta_12, delta_34)
            leading_blocks.append(lb)
            current_pol_list = []

            for k in range(1, k_max + 1):
                if l <= l_max:
                    if self.delta_residue(nu, k, l, delta_12, delta_34, 1) != 0:
                        current_pol_list.append((k, k, l + k, 1))

                if k % 2 == 0:
                    if self.delta_residue(nu, k // 2, l, delta_12, delta_34, 2) != 0:
                        current_pol_list.append((k, k // 2, l, 2))

                if k <= l:
                    if self.delta_residue(nu, k, l, delta_12, delta_34, 3) != 0:
                        current_pol_list.append((k, k, l - k, 3))

                if l == 0:
                    r_powers.append(r_powers[k].mul_matrix(r_powers[1]))

            # These are in the format (n, k, l, series)
            pol_list.append(current_pol_list)
            res_list.append([])
            pow_list.append([])
            den_list.append([])
            new_res_list.append([])
            old_den_list.append([])

        old_res_list = MeromorphicBlockVector(leading_blocks[0])
        # Initialize the residues at the appropriate leading blocks
        for l in range(0, l_max + k_max + 1):
            for i in range(0, len(pol_list[l])):
                l_new = pol_list[l][i][2]
                res_list[l].append(MeromorphicBlockVector(leading_blocks[l_new]))

                pow_list[l].append(0)
                den_list[l].append(1)
                new_res_list[l].append(0)
                old_den_list[l].append(1)

        for k in range(1, k_max + 1):
            for l in range(0, l_max + k_max + 1):
                for i in range(0, len(res_list[l])):
                    if pow_list[l][i] >= k_max:
                        continue

                    res = self.delta_residue(nu, pol_list[l][i][1], l, delta_12, delta_34, pol_list[l][i][3])
                    pow_list[l][i] += pol_list[l][i][0]

                    for j in range(0, len(res_list[l][i].chunks)):
                        r_sub = r_powers[pol_list[l][i][0]].submatrix(0, derivative_order - j, 0, derivative_order - j)
                        res_list[l][i].chunks[j] = r_sub.mul_matrix(res_list[l][i].chunks[j]).mul_scalar(res)

            for l in range(0, l_max + k_max + 1):
                for i in range(0, len(res_list[l])):
                    if pow_list[l][i] >= k_max:
                        continue

                    l_new = pol_list[l][i][2]
                    new_res_list[l][i] = MeromorphicBlockVector(leading_blocks[l_new])

                    prod = 1
                    current_pol_list = []
                    pole1 = delta_pole(nu, pol_list[l][i][1], l, pol_list[l][i][3]) + pol_list[l][i][0]

                    if dim % 2 == 0:
                        for i_new in range(0, len(res_list[l_new])):
                            pole2 = delta_pole(nu, pol_list[l_new][i_new][1], l_new, pol_list[l_new][i_new][3])
                            current_pol_list.append(pole2)
                            prod *= (pole1 - pole2) * old_den_list[l_new][i_new]

                        den_list[l][i] = prod
                        for j in range(0, len(new_res_list[l][i].chunks)):
                            new_res_list[l][i].chunks[j] = new_res_list[l][i].chunks[j].mul_scalar(prod)

                    for i_new in range(0, len(res_list[l_new])):
                        pole2 = delta_pole(nu, pol_list[l_new][i_new][1], l_new, pol_list[l_new][i_new][3])

                        if dim % 2 == 0:
                            fact = omit_all(current_pol_list, [pole2], pole1)
                            for i_other in range(0, len(res_list[l_new])):
                                if i_other != i_new:
                                    fact *= old_den_list[l_new][i_other]
                        else:
                            fact = eval_mpfr(1, prec) / eval_mpfr(pole1 - pole2, prec)

                        for j in range(0, len(old_res_list.chunks)):
                            for n in range(0, old_res_list.chunks[j].nrows()):
                                element = res_list[l_new][i_new].chunks[j].get(n, 0)
                                element = element * fact
                                element = element.expand()
                                old_res_list.chunks[j].set(n, 0, element)
                            new_res_list[l][i].chunks[j] = new_res_list[l][i].chunks[j].add_matrix(old_res_list.chunks[j])

            for l in range(0, l_max + k_max + 1):
                for i in range(0, len(res_list[l])):
                    if pow_list[l][i] >= k_max:
                        continue

                    if "expand" in dir(den_list[l][i]):
                        den_list[l][i] = den_list[l][i].expand()
                    old_den_list[l][i] = den_list[l][i]

                    for j in range(0, len(res_list[l][i].chunks)):
                         res_list[l][i].chunks[j] = new_res_list[l][i].chunks[j]

        # Divide by the common denominator again
        if dim % 2 == 0:
            for l in range(0, l_max + k_max + 1):
                for i in range(0, len(res_list[l])):
                    if "expand" in dir(den_list[l][i]):
                        den_list[l][i] = den_list[l][i].expand()

                    for j in range(0, len(res_list[l][i].chunks)):
                        for n in range(0, res_list[l][i].chunks[j].nrows()):
                            element = res_list[l][i].chunks[j].get(n, 0)
                            element = element.expand()
                            element = element / den_list[l][i]
                            element = element.expand()
                            element = element.subs(aux, 0)
                            res_list[l][i].chunks[j].set(n, 0, element)

        # Perhaps poorly named, S keeps track of a linear combination of derivatives
        # We get this by including the essential singularity, then stripping it off again
        s_matrix = DenseMatrix(derivative_order + 1, derivative_order + 1, [0] * ((derivative_order + 1) ** 2))
        for i in range(0, derivative_order + 1):
            new_element = 1
            for j in range(i, -1, -1):
                s_matrix.set(i, j, new_element)
                new_element *= (j / ((i - j + 1) * r_cross)) * (delta - (i - j))

        for l in range(0, l_max + 1, step):
            conformal_block = ConformalBlockVector(dim, l, delta_12, delta_34, m_max + 2 * n_max, k_max, s_matrix, leading_blocks[l], pol_list[l], res_list[l])
            conformal_blocks.append(conformal_block)
            self.table.append(PolynomialVector([], [l, 0], conformal_block.large_poles))

        a = symbols('a')
        b = symbols('b')
        hack = symbols('hack')
        old_coeff_grid = []

        rules1 = []
        rules2 = []
        old_expression1 = sqrt(a ** 2 - b) / (hack + sqrt((hack - a) ** 2 - b) + hack * sqrt(hack - a + sqrt((hack - a) ** 2 - b)))
        old_expression2 = (hack - sqrt((hack - a) ** 2 - b)) / sqrt(a ** 2 - b)

        for n in range(0, m_max + 2 * n_max + 1):
            old_coeff_grid.append([0] * (m_max + 2 * n_max + 1))

        for n in range(0, n_max + 1):
            for m in range(0, 2 * (n_max - n) + m_max + 1):
                if n == 0 and m == 0:
                    expression1 = old_expression1
                    expression2 = old_expression2
                elif m == 0:
                    old_expression1 = old_expression1.diff(b)
                    old_expression2 = old_expression2.diff(b)
                    expression1 = old_expression1
                    expression2 = old_expression2
                else:
                    expression1 = expression1.diff(a)
                    expression2 = expression2.diff(a)

                rules1.append(expression1.subs({hack : eval_mpfr(2, prec), a : 1, b : 0}))
                rules2.append(expression2.subs({hack : eval_mpfr(2, prec), a : 1, b : 0}))
                self.m_order.append(m)
                self.n_order.append(n)

        # If b is always 0, then eta is always 1
        if n_max == 0:
            _x = symbols('_x')
            r = function_symbol('r', a)
            g = function_symbol('g', r)

            for m in range(0, derivative_order + 1):
                if m == 0:
                    old_expression = g
                    g = function_symbol('g', _x)
                else:
                    old_expression = old_expression.diff(a)

                expression = old_expression
                for i in range(1, m + 1):
                    expression = expression.subs(Derivative(r, [a] * i), rules1[i])

                for l in range(0, len(conformal_blocks)):
                    new_deriv = expression
                    for i in range(1, m + 1):
                        new_deriv = new_deriv.subs(Subs(Derivative(g, [_x] * i), [_x], [r]), conformal_blocks[l].chunks[0].get(i, 0))
                    if m == 0:
                        new_deriv = conformal_blocks[l].chunks[0].get(0, 0)
                    self.table[l].vector.append(new_deriv.expand())

            # Prevent further execution
            n_max = -1

        r = function_symbol('r', a, b)
        eta = function_symbol('eta', a, b)
        old_coeff_grid[0][0] = 1
        order = 0

        for n in range(0, n_max + 1):
            for m in range(0, 2 * (n_max - n) + m_max + 1):
                # Hack implementation of the g(r(a, b), eta(a, b)) chain rule
                if n == 0 and m == 0:
                    coeff_grid = self.deepcopy(old_coeff_grid)
                elif m == 0:
                    for i in range(m + n - 1, -1, -1):
                        for j in range(m + n - i - 1, -1, -1):
                            coeff = old_coeff_grid[i][j]
                            if type(coeff) == type(1):
                                coeff_deriv = 0
                            else:
                                coeff_deriv = coeff.diff(b)
                            old_coeff_grid[i + 1][j] += coeff * r.diff(b)
                            old_coeff_grid[i][j + 1] += coeff * eta.diff(b)
                            old_coeff_grid[i][j] = coeff_deriv
                    coeff_grid = self.deepcopy(old_coeff_grid)
                else:
                    for i in range(m + n - 1, -1, -1):
                        for j in range(m + n - i - 1, -1, -1):
                            coeff = coeff_grid[i][j]
                            if type(coeff) == type(1):
                                coeff_deriv = 0
                            else:
                                coeff_deriv = coeff.diff(a)
                            coeff_grid[i + 1][j] += coeff * r.diff(a)
                            coeff_grid[i][j + 1] += coeff * eta.diff(a)
                            coeff_grid[i][j] = coeff_deriv

                # Replace r and eta derivatives with the rules found above
                deriv = self.deepcopy(coeff_grid)
                for l in range(order, 0, -1):
                    for i in range(0, m + n + 1):
                        for j in range(0, m + n - i + 1):
                            if type(deriv[i][j]) != type(1):
                                deriv[i][j] = deriv[i][j].subs(Derivative(r, [a] * self.m_order[l] + [b] * self.n_order[l]), rules1[l])
                                deriv[i][j] = deriv[i][j].subs(Derivative(r, [b] * self.n_order[l] + [a] * self.m_order[l]), rules1[l])
                                deriv[i][j] = deriv[i][j].subs(Derivative(eta, [a] * self.m_order[l] + [b] * self.n_order[l]), rules2[l])
                                deriv[i][j] = deriv[i][j].subs(Derivative(eta, [b] * self.n_order[l] + [a] * self.m_order[l]), rules2[l])

                # Replace conformal block derivatives similarly for each spin
                for l in range(0, len(conformal_blocks)):
                    new_deriv = 0
                    for i in range(0, m + n + 1):
                        for j in range(0, m + n - i + 1):
                            new_deriv += deriv[i][j] * conformal_blocks[l].chunks[j].get(i, 0)
                    self.table[l].vector.append(new_deriv.expand())
                order += 1

    def dump(self, name):
        dump_table_contents(self, name)

    def deepcopy(self, array):
        ret = []
        for el in array:
            ret.append(list(el))
        return ret

    def delta_residue(self, nu, k, l, delta_12, delta_34, series):
        """
        Returns the residue of a meromorphic global conformal block at a particular
        pole in `delta`. These residues were found by Kos, Poland and Simmons-Duffin
        in arXiv:1406.4858.

        Parameters
        ----------
        nu:       `(d - 2) / 2` where d is the spatial dimension. If this number is
                  not an integer, the residue will always be strictly between 0 and
                  inf. Otherwise, the code might encounter factors of 0 in the
                  numerator or denominator. These are replaced by `aux` which is the
                  fractional part of `nu`.
        k:        The parameter k indexing the various poles. As described in
                  arXiv:1406.4858, it may be any positive integer unless `series`
                  is 3.
        l:        The spin.
        delta_12: The difference between the external scaling dimensions of operator
                  1 and operator 2.
        delta_34: The difference between the external scaling dimensions of operator
                  3 and operator 4.
        series:   The parameter i desribing the three types of poles in
                  arXiv:1406.4858.
        """
        zero = 0
        two = eval_mpfr(2, prec)
        check_numerator = False
        # Time saving special case
        if series != 2 and k % 2 != 0 and delta_12 == 0 and delta_34 == 0:
            return 0
        elif nu % 1 == 0:
            nu = int(nu)
            zero = aux

        if series == 1:
            ret = - ((k * (-4) ** k) / (factorial(k) ** 2)) * sympy.rf((1 - k + delta_12) / two, k) * sympy.rf((1 - k + delta_34) / two, k)
            if l == 0 and nu == 0:
                # Take l to 0, then nu
                return ret * 2
            else:
                return ret * (sympy.rf(l + 2 * nu, k) / sympy.rf(l + nu, k))
        elif series == 2:
            ret = ((k * sympy.rf(nu + 1, k - 1)) / (factorial(k) ** 2))
            factors = [l + nu + 1 - delta_12, l + nu + 1 + delta_12, l + nu + 1 - delta_34, l + nu + 1 + delta_34]

            if l + nu == k:
                ret *= zero / (l + nu + k)
            else:
                ret *= (l + nu - k) / (l + nu + k)

            if k >= l + nu and (l + nu - k) % 2 == 0:
                ret *= -4 * sympy.rf(-nu, nu) * factorial(k - nu) / (zero * (sympy.rf((l + nu - k + 1) / 2, k) * sympy.rf((l + nu - k) / 2, (k - l - nu) / 2) * factorial(((l + nu - k) / 2) + (k - 1))) ** 2)
            elif k >= l + nu + 1 and (l + nu + 1 - k) % 2 == 0:
                ret *= -4 * sympy.rf(-nu, nu) * factorial(k - nu) / (zero * (sympy.rf((l + nu - k) / 2, k) * sympy.rf((l + nu - k + 1) / 2, (k - 1 - l - nu) / 2) * factorial(((l + nu - k + 1) / 2) + (k - 1))) ** 2)
            elif k >= nu and nu % 1 == 0:
                ret *= -sympy.rf(-nu, nu) * factorial(k - nu) * zero / ((sympy.rf((l + nu - k + 1) / 2, k) * sympy.rf((l + nu - k) / 2, k)) ** 2)
            else:
                ret *= sympy.rf(-nu, k + 1) / ((sympy.rf((l + nu - k + 1) / 2, k) * sympy.rf((l + nu - k) / 2, k)) ** 2)

            for f in factors:
                if -k < f <= k and (f - k) % 2 == 0:
                    ret *= sympy.rf((f - k) / 2, (k - f) / 2) * factorial(((f + k) / 2) - 1) * zero / 2
                else:
                    ret *= sympy.rf((f - k) / 2, k)

            return ret.expand()
        else:
            return - ((k * (-4) ** k) / (factorial(k) ** 2)) * (sympy.rf(1 + l - k, k) * sympy.rf((1 - k + delta_12) / two, k) * sympy.rf((1 - k + delta_34) / two, k) / sympy.rf(1 + nu + l - k, k))

class ConformalBlockTable:
    """
    A class which calculates tables of conformal block derivatives when initialized.
    This uses recursion relations on the diagonal found by Hogervorst, Osborn and
    Rychkov in arXiv:1305.1321.

    Parameters
    ----------
    dim:       The spatial dimension. If even dimensions are of interest, floating
               point numbers with small fractional parts are recommended.
    k_max:     Number controlling the accuracy of the rational approximation.
               Specifically, it is the maximum power of the crossing symmetric value
               of the radial co-ordinate as described in arXiv:1406.4858.
    l_max:     The maximum spin to include in the table.
    m_max:     Number controlling how many `a` derivatives to include where the
               standard co-ordinates are expressed as `(a + sqrt(b)) / 2` and
               `(a - sqrt(b)) / 2`. As explained in arXiv:1412.4127, a value of 0
               does not necessarily eliminate all `a` derivatives.
    n_max:     The number of `b` derivatives to include where the standard
               co-ordinates are expressed as `(a + sqrt(b)) / 2` and
               `(a - sqrt(b)) / 2`.
    delta_12:  [Optional] The difference between the external scaling dimensions of
               operator 1 and operator 2. Defaults to 0.
    delta_34:  [Optional] The difference between the external scaling dimensions of
               operator 3 and operator 4. Defaults to 0.
    odd_spins: [Optional] Whether to include 0, 1, 2, 3, ..., `l_max` instead of
               just 0, 2, 4, ..., `l_max`. Defaults to `False`.
    name:      [Optional] The name of a file containing conformal blocks that have
               already been calculated. If this is specified, all other parameters
               passed to the class are overwritten by the ones in the table.

    Attributes
    ----------
    table:     A list of `PolynomialVector`s. A block's position in the table is
               equal to its spin if `odd_spins` is True. Otherwise it is equal to
               half of the spin.
    m_order:   A list with the same number of components as the `PolynomialVector`s
               in `table`. Any `i`-th entry in a `PolynomialVector` is a particular
               derivative of a conformal block, but to remember which one, just look
               at the `i`-th entry of `m_order` which is the number of `a`
               derivatives.
    n_order:   A list with the same number of components as the `PolynomialVector`s
               in `table`. Any `i`-th entry in a `PolynomialVector` is a particular
               derivative of a conformal block, but to remember which one, just look
               at the `i`-th entry of `n_order` which is the number of `b`
               derivatives.
    """
    def __init__(self, dim, k_max, l_max, m_max, n_max, delta_12 = 0, delta_34 = 0, odd_spins = False, name = None):
        self.dim = dim
        self.k_max = k_max
        self.l_max = l_max
        self.m_max = m_max
        self.n_max = n_max
        self.delta_12 = delta_12
        self.delta_34 = delta_34
        self.odd_spins = odd_spins

        if name != None:
            dump_file = open(name, 'r')
            command = dump_file.read()
            exec(command)
            return

        small_table = ConformalBlockTableSeed(dim, k_max, l_max, min(m_max + 2 * n_max, 3), 0, delta_12, delta_34, odd_spins)
        self.m_order = small_table.m_order
        self.n_order = small_table.n_order
        self.table = small_table.table

        a = symbols('a')
        nu = eval_mpfr(sympy.Rational(dim, 2) - 1, prec)
        c_2 = (ell * (ell + 2 * nu) + delta * (delta - 2 * nu - 2)) / 2
        c_4 = ell * (ell + 2 * nu) * (delta - 1) * (delta - 2 * nu - 1)
        polys = [0, 0, 0, 0, 0]
        poly_derivs = [[], [], [], [], []]
        delta_prod = delta_12 * delta_34 / (eval_mpfr(-2, prec))
        delta_sum = (delta_12 - delta_34) / (eval_mpfr(-2, prec))

        # Polynomial 0 goes with the lowest order derivative on the right hand side
        # Polynomial 3 goes with the highest order derivative on the right hand side
        # Polynomial 4 goes with the derivative for which we are solving
        polys[0] += (a ** 0) * (16 * c_2 * (2 * nu + 1) - 8 * c_4)
        polys[0] += (a ** 1) * (4 * (c_4 + 2 * (2 * nu + 1) * (c_2 * delta_sum - c_2 + nu * delta_prod)))
        polys[0] += (a ** 2) * (2 * (delta_sum - nu) * (c_2 * (2 * delta_sum - 1) + delta_prod * (6 * nu - 1)))
        polys[0] += (a ** 3) * (2 * delta_prod * (delta_sum - nu) * (delta_sum - nu + 1))
        polys[1] += (a ** 1) * (-16 * c_2 * (2 * nu + 1))
        polys[1] += (a ** 2) * (4 * delta_prod - 24 * nu * delta_prod + 8 * nu * (2 * nu - 1) * (2 * delta_sum + 1) + 4 * c_2 * (1 - 4 * delta_sum + 6 * nu))
        polys[1] += (a ** 3) * (2 * c_2 * (4 * delta_sum - 2 * nu + 1) + 4 * (2 * nu - 1) * (2 * delta_sum + 1) * (delta_sum - nu + 1) + 2 * delta_prod * (10 * nu - 5 - 4 * delta_sum))
        polys[1] += (a ** 4) * ((delta_sum - nu + 1) * (4 * delta_prod + (2 * delta_sum + 1) * (delta_sum - nu + 2)))
        polys[2] += (a ** 2) * (16 * c_2 + 16 * nu - 32 * nu * nu)
        polys[2] += (a ** 3) * (8 * delta_prod - 8 * (3 * delta_sum - nu + 3) * (2 * nu - 1) - 16 * c_2 - 8 * nu + 16 * nu * nu)
        polys[2] += (a ** 4) * (4 * (c_2 - delta_prod + (3 * delta_sum - nu + 3) * (2 * nu - 1)) - 4 * delta_prod - 2 * (delta_sum - nu + 2) * (5 * delta_sum - nu + 5))
        polys[2] += (a ** 5) * (2 * delta_prod + (delta_sum - nu + 2) * (5 * delta_sum - nu + 5))
        polys[3] += (a ** 3) * (32 * nu - 16)
        polys[3] += (a ** 4) * (16 - 32 * nu + 4 * (4 * delta_sum - 2 * nu + 7))
        polys[3] += (a ** 5) * (4 * (2 * nu - 1) - 4 * (4 * delta_sum - 2 * nu + 7))
        polys[3] += (a ** 6) * (4 * delta_sum - 2 * nu + 7)
        polys[4] += (a ** 7) - 6 * (a ** 6) + 12 * (a ** 5) - 8 * (a ** 4)

        # Store all possible derivatives of these polynomials
        for i in range(0, 5):
            for j in range(0, i + 4):
                poly_derivs[i].append(polys[i].subs(a, 1))
                polys[i] = polys[i].diff(a)

        for m in range(self.m_order[-1] + 1, m_max + 2 * n_max + 1):
            for l in range(0, len(small_table.table)):
                new_deriv = 0
                for i in range(m - 1, max(m - 8, -1), -1):
                    coeff = 0
                    index = max(m - i - 4, 0)

                    prefactor = eval_mpfr(1, prec)
                    for k in range(0, index):
                        prefactor *= (m - 4 - k)
                        prefactor /= k + 1

                    k = max(4 + i - m, 0)
                    while k <= 4 and index <= (m - 4):
                        coeff += prefactor * poly_derivs[k][index]
                        prefactor *= (m - 4 - index)
                        prefactor /= index + 1
                        index += 1
                        k += 1

                    if type(coeff) != type(1):
                        coeff = coeff.subs(ell, small_table.table[l].label[0])
                    new_deriv -= coeff * self.table[l].vector[i]

                new_deriv = new_deriv / poly_derivs[4][0]
                self.table[l].vector.append(new_deriv.expand())

            self.m_order.append(m)
            self.n_order.append(0)

        # This is just an alternative to storing derivatives as a doubly-indexed list
        index = m_max + 2 * n_max + 1
        index_map = [range(0, m_max + 2 * n_max + 1)]

        for n in range(1, n_max + 1):
            index_map.append([])
            for m in range(0, 2 * (n_max - n) + m_max + 1):
                index_map[n].append(index)

                coeff1 = m * (-1) * (2 - 4 * n - 4 * nu)
                coeff2 = m * (m - 1) * (2 - 4 * n - 4 * nu)
                coeff3 = m * (m - 1) * (m - 2) * (2 - 4 * n - 4 * nu)
                coeff4 = 1
                coeff5 = (-6 + m + 4 * n - 2 * nu - 2 * delta_sum)
                coeff6 = (-1) * (4 * c_2 + m * m + 8 * m * n - 5 * m + 4 * n * n - 2 * n - 2 - 4 * nu * (1 - m - n) + 4 * delta_sum * (m + 2 * n - 2) + 2 * delta_prod)
                coeff7 = m * (-1) * (m * m + 12 * m * n - 13 * m + 12 * n * n - 34 * n + 22 - 2 * nu * (2 * n - m - 1) + 2 * delta_sum * (m + 4 * n - 5) + 2 * delta_prod)
                coeff8 = (1 - n)
                coeff9 = (1 - n) * (-6 + 3 * m + 4 * n - 2 * nu + 2 * delta_sum)

                for l in range(0, len(small_table.table)):
                    new_deriv = 0

                    if m > 0:
                        new_deriv += coeff1 * self.table[l].vector[index_map[n][m - 1]]
                    if m > 1:
                        new_deriv += coeff2 * self.table[l].vector[index_map[n][m - 2]]
                    if m > 2:
                        new_deriv += coeff3 * self.table[l].vector[index_map[n][m - 3]]

                    new_deriv += coeff4 * self.table[l].vector[index_map[n - 1][m + 2]]
                    new_deriv += coeff5 * self.table[l].vector[index_map[n - 1][m + 1]]
                    new_deriv += coeff6.subs(ell, small_table.table[l].label[0]) * self.table[l].vector[index_map[n - 1][m]]
                    new_deriv += coeff7 * self.table[l].vector[index_map[n - 1][m - 1]]

                    if n > 1:
                        new_deriv += coeff8 * self.table[l].vector[index_map[n - 2][m + 2]]
                        new_deriv += coeff9 * self.table[l].vector[index_map[n - 2][m + 1]]

                    new_deriv = new_deriv / (2 - 4 * n - 4 * nu)
                    self.table[l].vector.append(new_deriv.expand())

                self.m_order.append(m)
                self.n_order.append(n)
                index += 1

    def dump(self, name):
        """
        Saves a table of conformal block derivatives to a file. The file is valid
        Python code which manually populates the entries of `table` when executed.

        Parameters
        ----------
        name: The path to use for output.
        """
        dump_table_contents(self, name)

class ConvolvedBlockTable:
    """
    A class which produces the functions that need to be linearly dependent in a
    crossing symmetric CFT. If a `ConformalBlockTable` does not need to be changed
    after a change to the external dimensions, a `ConvolvedBlockTable` does not
    either. This is because external dimensions only appear symbolically through a
    symbol called `delta_ext`.

    Parameters
    ----------
    block_table: A `ConformalBlockTable` from which to produce the convolved blocks.
    odd_spins:   [Optional] A parameter telling the class to keep odd spins which is
                 only used if `odd_spins` is True for `block_table`. Defaults to
                 `True`.
    symmetric:   [Optional] Whether to add blocks in two different channels instead
                 of subtract them. Defaults to `False`.
    content:     [Optional] A list of ordered triples that are used to produce
                 user-defined linear combinations of convolved conformal blocks
                 instead of just individual convolved conformal blocks where all the
                 coefficients are 1. Elements of a triple are taken to be the
                 coefficient, the dimension shift and the spin shift respectively.
                 It should always make sense to include a triple whose second and
                 third entries are 0 and 0 since this corresponds to a convolved
                 conformal block with scaling dimension `delta` and spin `ell`.
                 However, if other blocks in the multiplet have `delta + 1` and
                 `ell - 1` relative to this, another triple should be included whose
                 second and third entries are 1 and -1. The coefficient (first
                 entry) may be a polynomial in `delta` with coefficients depending
                 on `ell`.

    Attributes
    ----------
    dim:         The spatial dimension, inherited from `block_table`.
    k_max:       Numer controlling the accuracy of the rational approximation,
                 inherited from `block_table`.
    l_max:       The highest spin kept in the convolved block table. This is at most
                 the `l_max` of `block_table`.
    m_max:       Number controlling how many `a` derivatives there are where the
                 standard co-ordinates are expressed as `(a + sqrt(b)) / 2` and
                 `(a - sqrt(b)) / 2`. This is at most the `m_max` of `block_table`.
    n_max:       The number of `b` derivatives there are where the standard
                 co-ordinates are expressed as `(a + sqrt(b)) / 2` and
                 `(a - sqrt(b)) / 2`. This is at most the `n_max` of `block_table`.
    table:       A list of `PolynomialVector`s. A block's position in the table is
                 equal to its spin if `odd_spins` is `True`. Otherwise it is equal
                 to half of the spin.
    m_order:     A list stating how many `a` derivatives are being described by the
                 corresponding entry in a `PolynomialVector` in `table`. Different
                 from the `m_order` of `block_table` because some derivatives vanish
                 by symmetry.
    n_order:     A list stating how many `b` derivatives are being described by the
                 corresponding entry in a `PolynomialVector` in `table`.
    """
    def __init__(self, block_table, odd_spins = True, symmetric = False, content = [[1, 0, 0]]):
        # Copying everything but the unconvolved table is fine from a memory standpoint
        self.dim = block_table.dim
        self.k_max = block_table.k_max
        self.l_max = block_table.l_max
        self.m_max = block_table.m_max
        self.n_max = block_table.n_max

        self.m_order = []
        self.n_order = []
        self.table = []

        max_spin_shift = 0
        for trip in content:
            max_spin_shift = max(max_spin_shift, trip[2])
        self.l_max -= max_spin_shift

        # We can restrict to even spin when the provided table has odd spin but not vice-versa
        if odd_spins == False and block_table.odd_spins == True:
            self.odd_spins = False
        else:
            self.odd_spins = block_table.odd_spins
        if block_table.odd_spins == True:
            step = 1
        else:
            step = 2

        symbol_array = []
        for n in range(0, block_table.n_max + 1):
            symbol_list = []
            for m in range(0, 2 * (block_table.n_max - n) + block_table.m_max + 1):
                symbol_list.append(symbols('g_' + n.__str__() + '_' + m.__str__()))
            symbol_array.append(symbol_list)

        derivatives = []
        for n in range(0, block_table.n_max + 1):
            for m in range(0, 2 * (block_table.n_max - n) + block_table.m_max + 1):
                # Skip the ones that will vanish
                if (symmetric == False and m % 2 == 0) or (symmetric == True and m % 2 == 1):
                    continue

                self.m_order.append(m)
                self.n_order.append(n)

                expression = 0
                old_coeff = eval_mpfr(sympy.Rational(1, 4), prec) ** delta_ext
                for j in range(0, n + 1):
                    coeff = old_coeff
                    for i in range(0, m + 1):
                        expression += coeff * symbol_array[n - j][m - i]
                        coeff *= (i + 2 * j - 2 * delta_ext) * (m - i) / (i + 1)
                    old_coeff *= (j - delta_ext) * (n - j) / (j + 1)

                deriv = expression / (factorial(m) * factorial(n))
                derivatives.append(deriv)

        spin = 0
        combined_block_table = []
        while spin <= self.l_max:
            vector = []
            l = spin // step

            # Different blocks in the linear combination may be divided by different poles
            all_poles = []
            for trip in content:
                del_shift = trip[1]
                ell_shift = trip[2] // step
                if l + ell_shift >= 0:
                    for p in block_table.table[l + ell_shift].poles:
                        new = True
                        for q in all_poles:
                            if abs(float(p - del_shift - q)) < 1e-10:
                                new = False
                                break
                        if new:
                            all_poles.append(p - del_shift)

            for i in range(0, len(block_table.table[l].vector)):
                entry = 0
                for trip in content:
                    if "subs" in dir(trip[0]):
                        coeff = trip[0].subs(ell, spin)
                    else:
                        coeff = trip[0]
                    del_shift = trip[1]
                    ell_shift = trip[2] // step

                    coeff *= r_cross ** del_shift
                    if l + ell_shift >= 0:
                        for p in all_poles:
                            new = True
                            for q in block_table.table[l + ell_shift].poles:
                                if abs(float(p + del_shift - q)) < 1e-10:
                                    new = False
                                    break
                            if new:
                                coeff *= delta - p
                        entry += coeff * block_table.table[l + ell_shift].vector[i].subs(delta, delta + del_shift)
                vector.append(entry.expand())

            combined_block_table.append(PolynomialVector(vector, [spin, 0], all_poles))
            if self.odd_spins:
                spin += 1
            else:
                spin += 2

        for l in range(0, len(combined_block_table)):
            new_derivs = []
            for i in range(0, len(derivatives)):
                deriv = derivatives[i]
                for j in range(len(combined_block_table[l].vector) - 1, 0, -1):
                    deriv = deriv.subs(symbol_array[block_table.n_order[j]][block_table.m_order[j]], combined_block_table[l].vector[j])
                new_derivs.append(2 * deriv.subs(symbol_array[0][0], combined_block_table[l].vector[0]))
            self.table.append(PolynomialVector(new_derivs, combined_block_table[l].label, combined_block_table[l].poles))

class SDP:
    """
    A class where convolved conformal blocks are augmented by crossing equations
    which allow numerical bounds to be derived. All calls to `SDPB` happen through
    this class.

    Parameters
    ----------
    dim_list:        A list of all scaling dimensions that appear in the external
                     operators of the four-point functions being considered. If
                     there is only one, this may be a float instead of a list.
    conv_table_list: A list of all types of convolved conformal block tables that
                     appear in the crossing equations. If there is only one type,
                     this may be a `ConvolvedBlockTable` instance instead of a list.
    vector_types:    [Optional] A list of triples, one for each type of operator in
                     the sum rule. The third element of each triple is the arbitrary
                     label for that representation (something used to label
                     `PolynomialVector`s that are generated). The second element is
                     an even integer for even spin operators and an odd integer for
                     odd spin operators. The first element is everything else.
                     Specifically, it is a list of matrices of ordered quadruples
                     where a matrix is a list of lists. If the sum rule involves no
                     matrices, it may simply be a list of ordered quadruples. In a
                     quadruple, the first entry is a numerical coefficient and the
                     second entry is an index stating which element of
                     `conv_table_list` that coefficient should multiply. The third
                     and fourth entries (which may be omitted if `dim_list` has only
                     one entry) specify the external dimensions that should replace
                     `delta_ext` in a `ConvolvedConformalBlockTable` as positions in
                     `dim_list`. They are the "inner two" dimensions `j` and `k` if
                     convolved conformal blocks are given `i`, `j`, `k`, `l` labels
                     as in arXiv:1406.4858. The first triple must describe the even
                     spin singlet channel (where the identity can be found). After
                     this, the order of the triples is not important.
    prototype:       [Optional] A previous instance of `SDP` which may speed up the
                     allocation of this one. The idea is that if a bound on any
                     operator does not need to change from one table to the next,
                     the bilinear basis corresponding to it (which requires a
                     Cholesky decomposition and a matrix inversion to calculate)
                     might simply be copied.

    Attributes
    ----------
    dim:             The spatial dimension, inherited from `conv_block_table_list`.
    k_max:           The corresponding attribute from `conv_block_table_list`.
    l_max:           The corresponding attribute from `conv_block_table_list`.
    m_max:           The corresponding attribute from `conv_block_table_list`.
    n_max:           The corresponding attribute from `conv_block_table_list`.
    odd_spins:       Whether any element of `conv_block_table_list` has odd spins.
    table:           A list of matrices of `PolynomialVector`s where the number of
                     rows and columns is determined from `vector_types`. They are
                     ordered first by the type of representation and then by spin.
                     Each `PolynomialVector` may be longer than a `PolynomialVector`
                     from a single entry of `conv_block_table_list`. They represent
                     the concatenation of several such `PolynomialVectors`, one for
                     each row of a vectorial sum rule.
    m_order:         Analogous to `m_order` in `ConformalBlockTable` or
                     `ConvolvedBlockTable`, this keeps track of the number of `a`
                     derivatives in these longer `PolynomialVector`s.
    m_order:         Analogous to `n_order` in `ConformalBlockTable` or
                     `ConvolvedBlockTable`, this keeps track of the number of `b`
                     derivatives in these longer `PolynomialVector`s.
    options:         A list of strings where each string is a command line option
                     that will be passed when `SDPB` is run from this `SDP`. This
                     list should be touched with `set_option` and not directly.
    points:          In addition to `PolynomialVector`s whose entries allow `delta`
                     to take any positive value, the user may also include in the
                     sum rule `PolynomialVector`s whose entries are pure numbers.
                     In other words, she may evaluate some of them once and for all
                     at particular values of `delta` to force certain operators to
                     appear in the spectrum. This list should be touched with
                     `add_point` and not directly.
    unit:            A list which gives the `PolynomialVector` corresponding to the
                     identity. This is obtained simply by plugging `delta = 0` into
                     the zero spin singlet channel. If such a channel involves
                     matrices, the sum of all elements is taken since the conformal
                     blocks are normalized under the convention that all OPE
                     coefficients involving the identity are 1. It should not be
                     necessary to change this.
    basis:           A list of matrices which has as many matrices as `table`.
                     Each triangular matrix stores a set of orthogonal polynomials
                     in the monomial basis. It should not be necessary to change
                     this.
    """
    def __init__(self, dim_list, conv_table_list, vector_types = [[[[[[1, 0, 0, 0]]]], 0, 0]], prototype = None):
        # If a user is looking at single correlators, we will not punish
        # her for only passing one dimension
        if type(dim_list) != type([]):
            dim_list = [dim_list]
        if type(conv_table_list) != type([]):
            conv_table_list = [conv_table_list]

        # Same story here
        self.dim = 0
        self.k_max = 0
        self.l_max = 0
        self.m_max = 0
        self.n_max = 0
        self.odd_spins = False

        # Just in case these are different
        for tab in conv_table_list:
            self.dim = max(self.dim, tab.dim)
            self.k_max = max(self.k_max, tab.k_max)
            self.l_max = max(self.l_max, tab.l_max)
            self.m_max = max(self.m_max, tab.m_max)
            self.n_max = max(self.n_max, tab.n_max)

        self.points = []
        self.m_order = []
        self.n_order = []
        self.table = []
        self.unit = []

        # Turn any "raw elements" from the vectorial sum rule into 1x1 matrices
        for i in range(0, len(vector_types)):
            for j in range(0, len(vector_types[i][0])):
                if type(vector_types[i][0][j][0]) != type([]):
                    vector_types[i][0][j] = [[vector_types[i][0][j]]]

        # Again, fill in arguments that need not be specified for single correlators   
        for i in range(0, len(vector_types)):
            for j in range(0, len(vector_types[i][0])):
                for k in range(0, len(vector_types[i][0][j])):
                    for l in range(0, len(vector_types[i][0][j][k])):
                        if len(vector_types[i][0][j][k][l]) == 2:
                            vector_types[i][0][j][k][l].append(0)
                            vector_types[i][0][j][k][l].append(0)

        # We must assume the 0th element put in vector_types corresponds to the singlet channel
        # This is because we must harvest the identity from it
        for matrix in vector_types[0][0]:
            chosen_tab = conv_table_list[matrix[0][0][1]]

            for i in range(0, len(chosen_tab.table[0].vector)):
                unit = 0
                for r in range(0, len(matrix)):
                    for s in range(0, len(matrix[r])):
                        quad = matrix[r][s]
                        tab = conv_table_list[quad[1]]
                        unit += quad[0] * tab.table[0].vector[i].subs(delta, 0).subs(delta_ext, (dim_list[quad[2]] + dim_list[quad[3]]) / 2.0)

                self.m_order.append(chosen_tab.m_order[i])
                self.n_order.append(chosen_tab.n_order[i])
                self.unit.append(unit)

        # Looping over types and spins gives "0 - S", "0 - T", "1 - A" and so on
        for vec in vector_types:
            if (vec[1] % 2) == 1:
                self.odd_spins = True
                start = 1
            else:
                start = 0

            for l in range(start, self.l_max, 2):
                size = len(vec[0][0])

                outer_list = []
                for r in range(0, size):
                    inner_list = []
                    for s in range(0, size):
                        derivatives = []
                        for matrix in vec[0]:
                            quad = matrix[r][s]
                            tab = conv_table_list[quad[1]]

                            if tab.odd_spins:
                                index = l
                            else:
                                index = l // 2

                            for i in range(0, len(tab.table[index].vector)):
                                derivatives.append(quad[0] * tab.table[index].vector[i].subs(delta_ext, (dim_list[quad[2]] + dim_list[quad[3]]) / 2.0))
                        inner_list.append(PolynomialVector(derivatives, [l, vec[2]], tab.table[index].poles))
                    outer_list.append(inner_list)
                self.table.append(outer_list)

        self.bounds = [0.0] * len(self.table)
        self.options = []

        if prototype == None:
            self.basis = [0] * len(self.table)
            self.set_bound(reset_basis = True)
        else:
            self.basis = []
            for mat in prototype.basis:
                self.basis.append(mat)
            self.set_bound(reset_basis = False)

    def add_point(self, spin_irrep = -1, dimension = -1):
        """
        Tells the `SDP` that a particular fixed operator should be included in the
        sum rule. If called with one argument, all points with that label will be
        removed. If called with no arguments, all points with any label will be
        removed.

        Parameters
        ----------
        spin_irrep: [Optional] An ordered pair used to label the `PolynomialVector`
                    for the operator. The first entry is the spin, the second is the
                    label which must be found in `vector_types` or 0 if not present.
                    Defaults to -1 which means all operators.
        dimension:  [Optional] The scaling dimension of the operator being added.
                    Defaults to -1 which means the point should be removed.
        """
        if spin_irrep == -1:
            self.points = []
            return

        if type(spin_irrep) == type(1):
            spin_irrep = [spin_irrep, 0]
        if dimension != -1:
            self.points.append((spin_irrep, dimension))
        else:
            i = 0
            while i < len(self.points):
                if self.points[i][0] == spin_irrep:
                    self.points = self.points[:i] + self.points[i + 1:]
                else:
                    i += 1

    def get_bound(self, gapped_spin_irrep):
        """
        Returns the minimum scaling dimension of a given operator in this `SDP`.
        This will return the unitarity bound until the user starts calling
        `set_bound`.

        Parameters
        ----------
        gapped_spin_irrep: An ordered pair used to label the `PolynomialVector`
                           whose bound should be read. The first entry is the spin
                           and the second is the label found in `vector_types` or
                           0 if not present.
        """
        if type(gapped_spin_irrep) == type(1):
            gapped_spin_irrep = [gapped_spin_irrep, 0]
        for l in range(0, len(self.table)):
                if self.table[l][0][0].label == gapped_spin_irrep:
                    return self.bounds[l]

    def set_bound(self, gapped_spin_irrep = -1, delta_min = -1, reset_basis = True):
        """
        Sets the minimum scaling dimension of a given operator in the sum rule. If
        called with one argument, the operator with that label will be assigned the
        unitarity bound. If called with no arguments, all operators will be assigned
        the unitarity bound.

        Parameters
        ----------
        gapped_spin_irrep: [Optional] An ordered pair used to label the
                           `PolynomialVector` whose bound should be set. The first
                           entry is the spin and the second is the label found in
                           `vector_types` or 0 if not present. Defaults to -1 which
                           means all operators.
        delta_min:         [Optional] The minimum scaling dimension to set. Defaults
                           to -1 which means unitarity.
        reset_basis:       [Optional] An internal parameter which may be used to
                           prevent the orthogonal polynomials which improve the
                           numerical stability of `SDPB` from being recalculated.
                           Defaults to `True`.
        """
        if gapped_spin_irrep == -1:
            for l in range(0, len(self.table)):
                spin = self.table[l][0][0].label[0]
                self.bounds[l] = unitarity_bound(self.dim, spin)

                if reset_basis:
                    self.set_basis(l)
        else:
            if type(gapped_spin_irrep) == type(1):
                gapped_spin_irrep = [gapped_spin_irrep, 0]

            for l in range(0, len(self.table)):
                if self.table[l][0][0].label == gapped_spin_irrep:
                    break
            spin = gapped_spin_irrep[0]

            if delta_min == -1:
                self.bounds[l] = unitarity_bound(self.dim, spin)
            else:
                self.bounds[l] = delta_min

            if reset_basis:
                self.set_basis(l)

    def set_option(self, key = None, value = None):
        """
        Sets the value of a switch that should be passed to `SDPB` on the command
        line. `SDPB` options that do not take a parameter are handled by other
        methods so it should not be necessary to pass them.

        Parameters
        ----------
        key:   [Optional] The name of the `SDPB` parameter being set without any
               "--" at the beginning or "=" at the end. No checking is done to
               ensure that it is a valid parameter. Defaults to `None` which means
               all parameters will be reset to their default values.
        value: [Optional] The string or numerical value that should accompany `key`.
               Defaults to `None` which means that the parameter for `key` will be
               reset to its default value.
        """
        if key == None:
            self.options = []
        else:
            found = False
            opt_string = "--" + key + "="
            for i in range(0, len(self.options)):
                if self.options[i][:len(opt_string)] == opt_string:
                    found = True
                    break
            if found == True and value == None:
                self.options = self.options[:i] + self.options[i + 1:]
            elif found == True and value != None:
                self.options[i] = opt_string + str(value)
            elif found == False and value != None:
                self.options.append(opt_string + str(value))

    def set_basis(self, index):
        """
        Calculates a basis of polynomials that are orthogonal with respect to the
        positive measure prefactor that turns a `PolynomialVector` into a rational
        approximation to a conformal block. It should not be necessary to explicitly
        call this.

        Parameters
        ----------
        index: The position of the matrix in `table` whose basis needs updating.
        """
        poles = self.table[index][0][0].poles
        delta_min = mpmath.mpf(self.bounds[index].__str__())        
        bands = []
        matrix = []

        degree = 0
        size = len(self.table[index])
        for r in range(0, size):
            for s in range(0, size):
                polynomial_vector = self.table[index][r][s].vector

                for n in range(0, len(polynomial_vector)):
                    expression = polynomial_vector[n].expand()

                    if type(expression) == type(eval_mpfr(1, 10)):
                        coeff_list = [expression]
                    else:
                        coeff_list = expression.args
                    degree = max(degree, len(coeff_list) - 1)

        for d in range(0, 2 * (degree // 2) + 1):
            result = self.integral(d, delta_min, poles)
            bands.append(result)
        for r in range(0, (degree // 2) + 1):
            new_entries = []
            for s in range(0, (degree // 2) + 1):
                new_entries.append(bands[r + s])
            matrix.append(new_entries)

        matrix = mpmath.matrix(matrix)
        matrix = mpmath.cholesky(matrix, tol = mpmath.mpf(1e-200))
        matrix = mpmath.inverse(matrix)
        self.basis[index] = matrix

    def reshuffle_with_normalization(self, vector, norm):
        """
        Converts between the Mathematica definition and the bootstrap definition of
        an SDP. As explained in arXiv:1502.02033, it is natural to normalize the
        functionals being found by demanding that they give 1 when acting on a
        particular `PolynomialVector`. `SDPB` on the other hand works with
        functionals that have a fixed leading component. This is an equivalent
        problem after a trivial reshuffling.

        Parameters
        ----------
        vector: The `vector` part of the `PolynomialVector` needing to be shuffled.
        norm:   The `vector` part of the `PolynomialVector` constrained to have
                unit action under the functional before the reshuffling.
        """
        norm_hack = []
        for el in norm:
            norm_hack.append(float(el))

        max_index = norm_hack.index(max(norm_hack, key = abs))
        const = vector[max_index] / norm[max_index]
        ret = []

        for i in range(0, len(norm)):
            ret.append(vector[i] - const * norm[i])

        ret = [const] + ret[:max_index] + ret[max_index + 1:]
        return ret

    def get_index(self, array, element):
        """
        Finds where an element occurs in an array or -1 if not present.

        Parameters
        ----------
        array:   The array.
        element: The element.
        """
        if element in array:
            return array.index(element)
        else:
            return -1

    def extract_power(self, term):
        """
        Returns the degree of a single term in a polynomial. Symengine stores these
        as (coefficient, (delta, exponent)). This is helpful for sorting polynomials
        which are not sorted by default.

        Parameters
        ----------
        term: The symengine formula for a momomial.
        """
        if term.args == ():
            return 0
        elif term.args[1].args == ():
            return 1
        else:
            return term.args[1].args[1]

    def make_laguerre_points(self, degree):
        """
        Returns a list of convenient sample points for the XML files of `SDPB`.

        Parameters
        ----------
        degree: The maximum degree of all polynomials in a `PolynomialVector`.
        """
        ret = []
        for d in range(0, degree + 1):
            point = -(pi ** 2) * ((4 * d - 1) ** 2) / (64 * (degree + 1) * log(r_cross))
            ret.append(eval_mpfr(point, prec))
        return ret

    def shifted_prefactor(self, poles, base, x, shift):
        """
        Returns the positive measure prefactor that turns a `PolynomialVector` into
        a rational approximation to a conformal block. Evaluating this at a sample
        point produces a sample scaling needed by the XML files of `SDPB`.

        Parameters
        ----------
        poles: The roots of the prefactor's denominator, often from the `poles`
               attribute of a `PolynomialVector`.
        base:  The base of the exponential in the numerator, often the crossing
               symmetric value of the radial co-ordinate.
        x:     The argument of the function, often `delta`.
        shift: An amount by which to shift `x`. This should match one of the minimal
               values assigned by `set_bound`.
        """
        product = 1
        for p in poles:
            product *= x - (p - shift)
        return (base ** (x + shift)) / product

    def integral(self, pos, shift, poles):
        """
        Returns the inner product of two monic monomials with respect to the
        positive measure prefactor that turns a `PolynomialVector` into a rational
        approximation to a conformal block.

        Parameters
        ----------
        pos:   The sum of the degrees of the two monomials.
        shift: An amount by which to shift `delta`, the variable of integration.
        poles: The roots of the prefactor's denominator, often from the `poles`
               attribute of a `PolynomialVector`. Poles may be repeated up to
               twice which is the greatest amount of repetition in any real
               conformal block.
        """
        single_poles = []
        double_poles = []
        ret = mpmath.mpf(0)

        for p in poles:
            p = mpmath.mpf(str(p))

            if (p - shift) in single_poles:
                single_poles.remove(p - shift)
                double_poles.append(p - shift)
            elif (p - shift) < 0:
                single_poles.append(p - shift)

        for i in range(0, len(single_poles)):
            denom = mpmath.mpf(1)
            pole = single_poles[i]
            other_single_poles = single_poles[:i] + single_poles[i + 1:]
            for p in other_single_poles:
                denom *= pole - p
            for p in double_poles:
                denom *= (pole - p) ** 2
            ret += (mpmath.mpf(1) / denom) * (rho_cross ** pole) * ((-pole) ** pos) * mpmath.factorial(pos) * mpmath.gammainc(-pos, a = pole * mpmath.log(rho_cross))

        for i in range(0, len(double_poles)):
            denom = mpmath.mpf(1)
            pole = double_poles[i]
            other_double_poles = double_poles[:i] + double_poles[i + 1:]
            for p in other_double_poles:
                denom *= (pole - p) ** 2
            for p in single_poles:
                denom *= pole - p
            # Contribution of the most divergent part
            ret += (mpmath.mpf(1) / (pole * denom)) * ((-1) ** (pos + 1)) * mpmath.factorial(pos) * ((mpmath.log(rho_cross)) ** (-pos))
            ret -= (mpmath.mpf(1) / denom) * (rho_cross ** pole) * ((-pole) ** (pos - 1)) * mpmath.factorial(pos) * mpmath.gammainc(-pos, a = pole * mpmath.log(rho_cross)) * (pos + pole * mpmath.log(rho_cross))

            factor = 0
            for p in other_double_poles:
                factor -= mpmath.mpf(2) / (pole - p)
            for p in single_poles:
                factor -= mpmath.mpf(1) / (pole - p)
            # Contribution of the least divergent part
            ret += (factor / denom) * (rho_cross ** pole) * ((-pole) ** pos) * mpmath.factorial(pos) * mpmath.gammainc(-pos, a = pole * mpmath.log(rho_cross))

        return (rho_cross ** shift) * ret

    def write_xml(self, obj, norm, name = "mySDP"):
        """
        Outputs an XML file decribing the `table`, `bounds`, `points` and `basis`
        for this `SDP` in a format that `SDPB` can use to check for solvability.

        Parameters
        ----------
        obj:  Objective vector (often the `vector` part of a `PolynomialVector`)
              whose action under the found functional should be maximized.
        norm: Normalization vector (often the `vector` part of a `PolynomialVector`)
              which should have unit action under the functionals.
        name: [Optional] Name of the XML file to produce without any ".xml" at the
              end. Defaults to "mySDP".
        """
        obj = self.reshuffle_with_normalization(obj, norm)
        laguerre_points = []
        laguerre_degrees = []
        extra_vectors = []

        # Handle discretely added points
        for p in self.points:
            for l in range(0, len(self.table)):
                if self.table[l][0][0].label == p[0]:
                    break

            size = len(self.table[l])
            outer_list = []
            for r in range(0, size):
                inner_list = []
                for s in range(0, size):
                    new_vector = []
                    for i in range(0, len(self.table[l][r][s].vector)):
                        new_vector.append(self.table[l][r][s].vector[i].subs(delta, p[1]))
                    inner_list.append(PolynomialVector(new_vector, p[0], self.table[l][r][s].poles))
                outer_list.append(inner_list)
            extra_vectors.append(outer_list)
        self.table += extra_vectors

        doc = xml.dom.minidom.Document()
        root_node = doc.createElement("sdp")
        doc.appendChild(root_node)

        objective_node = doc.createElement("objective")
        matrices_node = doc.createElement("polynomialVectorMatrices")
        root_node.appendChild(objective_node)
        root_node.appendChild(matrices_node)

        # Here, we use indices that match the SDPB specification
        for n in range(0, len(obj)):
            elt_node = doc.createElement("elt")
            elt_node.appendChild(doc.createTextNode(obj[n].__str__()))
            objective_node.appendChild(elt_node)

        for j in range(0, len(self.table)):
            size = len(self.table[j])

            matrix_node = doc.createElement("polynomialVectorMatrix")
            rows_node = doc.createElement("rows")
            cols_node = doc.createElement("cols")
            elements_node = doc.createElement("elements")
            sample_point_node = doc.createElement("samplePoints")
            sample_scaling_node = doc.createElement("sampleScalings")
            bilinear_basis_node = doc.createElement("bilinearBasis")
            rows_node.appendChild(doc.createTextNode(size.__str__()))
            cols_node.appendChild(doc.createTextNode(size.__str__()))

            degree = 0
            if j >= len(self.bounds):
                delta_min = 0
            else:
                delta_min = self.bounds[j]

            for r in range(0, size):
                for s in range(0, size):
                    polynomial_vector = self.reshuffle_with_normalization(self.table[j][r][s].vector, norm)
                    vector_node = doc.createElement("polynomialVector")

                    for n in range(0, len(polynomial_vector)):
                        expression = polynomial_vector[n].expand()
                        # Impose unitarity bounds and the specified gap
                        expression = expression.subs(delta, delta + delta_min).expand()

                        if type(expression) == type(eval_mpfr(1, 10)):
                            coeff_list = [expression]
                        else:
                            coeff_list = sorted(expression.args, key = self.extract_power)
                        degree = max(degree, len(coeff_list) - 1)
                        if coeff_list == []:
                            coeff_list = [0.0]

                        polynomial_node = doc.createElement("polynomial")
                        for d in range(0, len(coeff_list)):
                            if d == 0:
                                coeff = eval_mpfr(coeff_list[0], prec)
                            else:
                                coeff = eval_mpfr(coeff_list[d].args[0], prec)
                    
                            coeff_node = doc.createElement("coeff")
                            coeff_node.appendChild(doc.createTextNode(coeff.__str__()))
                            polynomial_node.appendChild(coeff_node)
                        vector_node.appendChild(polynomial_node)
                    elements_node.appendChild(vector_node)

            poles = self.table[j][0][0].poles
            index = self.get_index(laguerre_degrees, degree)
            if j >= len(self.bounds):
                points = [self.points[j - len(self.bounds)][1]]
            elif index == -1:
                points = self.make_laguerre_points(degree)
                laguerre_points.append(points)
                laguerre_degrees.append(degree)
            else:
                points = laguerre_points[index]

            for d in range(0, degree + 1):
                elt_node = doc.createElement("elt")
                elt_node.appendChild(doc.createTextNode(points[d].__str__()))
                sample_point_node.appendChild(elt_node)
                damped_rational = self.shifted_prefactor(poles, r_cross, points[d], eval_mpfr(delta_min, prec))
                elt_node = doc.createElement("elt")
                elt_node.appendChild(doc.createTextNode(damped_rational.__str__()))
                sample_scaling_node.appendChild(elt_node)

            matrix = []
            if j >= len(self.bounds):
                delta_min = mpmath.mpf(delta_min.__str__())
                result = self.integral(0, delta_min, poles)
                result = 1.0 / mpmath.sqrt(result)
                matrix = mpmath.matrix([result])
            else:
                matrix = self.basis[j]

            for d in range(0, (degree // 2) + 1):
                polynomial_node = doc.createElement("polynomial")
                for q in range(0, d + 1):
                    coeff_node = doc.createElement("coeff")
                    coeff_node.appendChild(doc.createTextNode(matrix[d, q].__str__()))
                    polynomial_node.appendChild(coeff_node)
                bilinear_basis_node.appendChild(polynomial_node)

            matrix_node.appendChild(rows_node)
            matrix_node.appendChild(cols_node)
            matrix_node.appendChild(elements_node)
            matrix_node.appendChild(sample_point_node)
            matrix_node.appendChild(sample_scaling_node)
            matrix_node.appendChild(bilinear_basis_node)
            matrices_node.appendChild(matrix_node)

        self.table = self.table[:len(self.bounds)]
        xml_file = open(name + ".xml", 'w')
        doc.writexml(xml_file, addindent = "    ", newl = '\n')
        xml_file.close()
        doc.unlink()

    def iterate(self, name = "mySDP"):
        """
        Returns `True` if this `SDP` with its current gaps represents an allowed CFT
        and `False` otherwise.

        Parameters
        ----------
        name:       [Optional] The name of the XML file generated in the process
                    without any ".xml" at the end. Defaults to "mySDP".
        """
        obj = [0.0] * len(self.table[0][0][0].vector)
        self.write_xml(obj, self.unit, name)

        with open(name + ".log", "a+") as log_file:
            subprocess.Popen(["sdpb", "-s", name + ".xml", "--maxThreads=" + str(MAX_THREADS), "--precision=" + str(prec), "--findPrimalFeasible", "--findDualFeasible", "--noFinalCheckpoint"] + self.options, stdout=log_file).wait()
        log_file.close()
        out_file = open(name + ".out", 'r')
        terminate_line = next(out_file)
        terminate_reason = terminate_line.partition(" = ")[-1]
        out_file.close()

        return terminate_reason == '"found primal feasible solution";\n'

    def bisect(self, lower, upper, threshold, spin_irrep):
        """
        Uses a binary search to find the maximum allowed gap in a particular type
        of operator before the CFT stops existing. The allowed value closest to the
        boundary is returned.

        Parameters
        ----------
        lower:      A scaling dimension for the operator known to be allowed.
        upper:      A scaling dimension for the operator known to be disallowed.
        threshold:  How accurate the bisection needs to be before returning.
        spin_irrep: An ordered pair of the type passed to `set_bound`. Used to
                    label the spin and representation of the operator whose
                    dimension is being bounded.
        """
        if type(spin_irrep) == type(1):
            spin_irrep = [spin_irrep, 0]

        old = self.get_bound(spin_irrep)
        while abs(upper - lower) > threshold:
            test = (lower + upper) / 2.0
            print("Trying " + test.__str__())

            self.set_bound(spin_irrep, test)
            result = self.iterate()
            if result == False:
                upper = test
            else:
                lower = test

        self.set_bound(spin_irrep, old)
        return lower

    def opemax(self, dimension, spin_irrep, name = "mySDP"):
        """
        Returns the maximum allowed value of the squared OPE coefficient for an
        operator with a prescribed scaling dimension, spin and global symmetry
        representation. It is best to compare several OPE coefficients so that
        numerical artifacts cancel out.

        Parameters
        ----------
        dimension:  The scaling dimension of the operator whose OPE coefficient is
                    being bounded.
        spin_irrep: An ordered pair of the type passed to `set_bound`. Used to label
                    the spin and representation of the operator whose OPE
                    coefficient is being bounded.
        name:       [Optional] Name of the XML file generated in the process without
                    any ".xml" at the end. Defaults to "mySDP".
        """
        if type(spin_irrep) == type(1):
            spin_irrep = [spin_irrep, 0]

        for l in range(0, len(self.table)):
            if self.table[l][0][0].label == spin_irrep:
                break

        if len(self.table[l]) > 1:
            print("Only supported for 1x1 matrices")
            return 0.0

        prod = 1
        for p in self.table[0][0][0].poles:
            prod *= -p

        obj = []
        norm = []
        for i in range(0, len(self.unit)):
            norm.append(self.table[l][0][0].vector[i].subs(delta, dimension))
            obj.append(self.unit[i] / prod)

        self.write_xml(obj, norm, name)
        with open(name + ".log", "a+") as log_file:
            subprocess.Popen(["sdpb", "-s", name + ".xml", "--maxThreads=" + str(MAX_THREADS), "--precision=" + str(prec), "--noFinalCheckpoint"] + self.options, stdout=log_file).wait()
        log_file.close()
        out_file = open(name + ".out", 'r')
        next(out_file)
        primal_line = next(out_file)
        out_file.close()

        primal_value = primal_line.partition(" = ")[-1][:-2]
        return float(primal_value)

    def solution_functional(self, dimension, spin_irrep, name = "mySDP"):
        """
        Returns a functional (list of numerical components) that serves as a
        solution to the `SDP`. Like `iterate`, this sets a bound, generates an XML
        file and calls `SDPB`. However, rather than stopping after it determines
        that the `SDP` is indeed solvable, it will finish the computation to find
        the actual functional.

        Parameters
        ----------
        dimension:  The minimum value of the scaling dimension to test.
        spin_irrep: An ordered pair of the type passed to `set_bound`. Used to label
                    the spin / representation of the operator being given a minimum
                    scaling dimension of `dimension`.
        name:       [Optional] The name of the XML file generated in the process
                    without any ".xml" at the end. Defaults to "mySDP".
        """
        if type(spin_irrep) == type(1):
            spin_irrep = [spin_irrep, 0]

        obj = [0.0] * len(self.table[0][0][0].vector)
        old = self.get_bound(spin_irrep)
        self.set_bound(spin_irrep, dimension)
        self.write_xml(obj, self.unit, name)
        self.set_bound(spin_irrep, old)

        with open(name + ".log", "a+") as log_file:
            subprocess.Popen(["sdpb", "-s", name + ".xml", "--maxThreads=" + str(MAX_THREADS), "--precision=" + str(prec), "--noFinalCheckpoint"] + self.options, stdout=log_file).wait()
        log_file.close()
        out_file = open(name + ".out", 'r')
        for i in range(0, 7):
            next(out_file)
        y_line = next(out_file)
        y_line = y_line.partition(" = ")[-1][1:-3]

        component_strings = y_line.split(", ")
        components = [eval_mpfr(1.0, prec)]
        for num in component_strings:
            command = "components.append(eval_mpfr(" + num + ", prec))"
            exec(command)

        return components

    def extremal_coefficients(self, dimensions, spin_irreps):
        """
        Once the full extremal spectrum is known, one can reconstruct the OPE
        coefficients that cause those convolved conformal blocks to sum to the
        `SDP`'s `unit`. This outputs a vector of squared OPE coefficients
        determined in this way.

        Parameters
        ----------
        dimensions:  A list of dimensions in the spectrum as returned by
                     `extremal_dimensions`. However, it must be the union of such
                     scaling dimensions over all possible `spin_irrep` inputs to
                     `extremal_dimensions`.
        spin_irreps: A list of ordered pairs of the type passed to
                     `extremal_dimensions` used to label the spin and global
                     symmetry representations of all operators that
                     `extremal_dimensions` can find. This list must be in the same
                     order used for `dimensions`.
        """
        zeros = min(len(dimensions), len(spin_irreps))
        for i in range(0, zeros):
            if type(spin_irreps[i]) == type(1):
                spin_irreps[i] = [spin_irreps[i], 0]

        extremal_blocks = []
        for i in range(0, zeros):
            for j in range(0, zeros):
                for l in range(0, len(self.table)):
                    if self.table[l][0][0].label == spin_irreps[j]:
                        break

                temp = 0
                if len(self.table[l]) > 1:
                    print("Only supported for 1x1 matrices")
                    return 0.0

                polynomial_vector = self.table[l][temp][temp].vector[i].subs(delta, dimensions[j])
                extremal_blocks.append(float(polynomial_vector))

        identity = DenseMatrix(zeros, 1, self.unit)
        extremal_matrix = DenseMatrix(zeros, zeros, extremal_blocks)
        inverse = extremal_matrix.inv()

        return inverse.mul_matrix(identity)

    def extremal_dimensions(self, functional, spin_irrep):
        """
        This finds the zeros of the resulting expression when a functional acts on
        `PolynomialVector`s. When the sum rule has matrices of `PolynomialVector`s,
        these matrices should be marginally between positive definite and negative
        definite when dimensions of operators in the extremal spectrum are
        substituted. The returned list consists of dimensions for a given spin and
        representation.

        Parameters
        ----------
        functional: A list of functional components of the type returned by
                    `solution_functional`.
        spin_irrep: An ordered pair used to label the type of operator whose
                    extremal dimensions are being found. The first entry is the spin
                    and the second entry is the representation label found in
                    `vector_types`.
        """
        if type(spin_irrep) == type(1):
            spin_irrep = [spin_irrep, 0]

        for l in range(0, len(self.table)):
            if self.table[l][0][0].label == spin_irrep:
                break

        entries = []
        size = len(self.table[l])
        for r in range(0, size):
            for s in range(0, size):
                inner_product = 0.0
                polynomial_vector = self.reshuffle_with_normalization(self.table[l][r][s].vector, self.unit)

                for i in range(0, len(self.table[l][r][s].vector)):
                    inner_product += functional[i] * polynomial_vector[i]
                    inner_product = inner_product.expand()

                entries.append(inner_product)

        matrix = DenseMatrix(size, size, entries)
        determinant = matrix.det().expand()

        if type(determinant) == type(eval_mpfr(1, 10)):
            coeff_list = [determinant]
        else:
            coeff_list = sorted(determinant.args, key = self.extract_power)
        if coeff_list == []:
            coeff_list = [0.0]

        coeffs = []
        for d in range(0, len(coeff_list)):
            if d == 0:
                coeffs.append(float(coeff_list[0]))
            else:
                coeffs.append(float(coeff_list[d].args[0]))

        poly = numpy.polynomial.Polynomial(coeffs)
        roots = poly.roots()

        ret = []
        bound = self.get_bound(spin_irrep)
        for dim in roots:
            if dim.imag > -1e-10 and dim.imag < 0.1 and dim.real > (bound - 0.01):
                ret.append(dim.real)
        return ret
