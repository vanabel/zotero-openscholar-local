# Maximum principles and comparison theorems for semilinear parabolic systems and their applications

G. Lu\* and B. D. Sleeman

Department of Mathematics and Computer Science, The University, Dundee DD1 4HN, Scotland

(MS received 6 August 1991. Revised MS received 23 July 1992)

# Synopsis

A fundamental comparison theorem is established for general semilinear parabolic systems via the notions of sectorial operators, analytic semigroups and the application of the Tychonoff Fixed Point Theorem. Based on this result, we establish a maximum principle for systems of general parabolic operators and general comparison theorems for parabolic systems with quasimonotone or mixed quasimonotone nonlinearities. These results cover and extend most currently used forms of maximum principles and comparison theorems. A global existence theorem for parabolic systems is derived as an application which, in particular, gives rise to some global existence results for Fujita type systems and certain generalisations.

# 1. Introduction

One of the most useful and widely known tools employed in the study of semilinear parabolic partial differential equations is the maximum principle. Although there exists a vast range of references in the literature which contribute in one way or another to the exploration and the development of the subject, the most outstanding one is the classic monograph $[25]$ of Protter and Weinberger. Other important works include $[8]$ which deals with parabolic problems and $[26]$ which brings together most of the important applications up to 1980.

Various comparison theorems based upon maximum principles have been developed and applied to many problems arising from different fields such as biology, chemical physics, neurophysiology and flame propagation in the past two decades. The most widely used form was presented by Fife and Tang $[6,7]$ under the condition that all nonlinearities are monotonely nondecreasing. Other conditions were considered by Terman $[28,29]$ and Grindrod and Sleeman $[15]$ .

A common feature throughout the development of comparison theorems has been to first exploit maximum principles for scalar equations and then to generalise to systems of equations.

In this paper we adopt a different approach and base the development on the use of the Tychonoff Fixed Point Theorem. The advantage of doing so is that, instead of setting up a normed space, we can construct a linear topological space by using the notion of a “seminorm”. Consequently, a fundamental comparison theorem is obtained and many currently known maximum principles for parabolic problems and associated comparison theorems are recovered as corollaries. The application of the fundamental comparison theorem goes beyond those mentioned above; for example, it plays a major role in a constructive approach to sub- and super-solutions for a class of semilinear parabolic problems [24]; its various applications include the qualitative study of the Fujita-type systems and their generalisations, and of Lotka-Volterra reaction-diffusion systems describing cooperative relationships between two species, as described for example in [16], [18] and [19].

The plan of this paper is as follows; after establishing the fundamental comparison theorem in Section 2, we derive a maximum principle for parabolic systems in Section 3, which includes the result of [25, Section 3.8]. Based on these two results, we obtain three distinct comparison theorems in Sections 4–6, which include most of the currently used comparison results as special cases. The methods of proof are completely different from those in the current literature. All these theorems are stated, with particular reference to the Cauchy problem and the Dirichlet problem, and facilitate the discussions of the problems encountered in the current literature, some of which will be dealt with elsewhere. In Sections 7 and 8, we apply the fundamental comparison theorem to certain systems of semilinear parabolic equations to obtain information about the global existence of their solutions. A particular example of a “Fujita-type” system is given as an application.

# 2. A fundamental comparison-existence theorem

In order to present the fundamental comparison theorem in a unified way and thus include both the Cauchy problem and the initial-boundary-value problem, it is convenient to employ such notions as that of a sectorial operator and an analytic semigroup.

Detailed accounts of these concepts and the relationship between a sectorial operator and an analytic semigroup can be found e.g. in $[17]$ and $[9,8]$ . Hence in the following we only briefly mention some necessary definitions and basic properties without proof, before we go on to the Tychonoff theorem and the statement of the fundamental comparison theorem.

Let $\Omega$ be an open set in $\mathbf{R}^n$ , the real $n$ -dimensional Euclidean space. A second-order elliptic differential operator is an expression of the form

$$
\sum_ {| \alpha | \leq 2} a _ {\alpha} (x) D ^ {\alpha} \equiv \sum_ {k = 0} ^ {2} \sum_ {\alpha_ {1} + \dots + \alpha_ {n} = k} a _ {\alpha_ {1} \dots \alpha_ {n}} (x) D _ {1} ^ {\alpha_ {1}} \dots D _ {n} ^ {\alpha_ {n}}, \tag {2.1}
$$

where the coefficients $a_{\alpha}(x)$ are defined in $\Omega$ and for any $x \in \Omega$

$$
\sum_ {| \alpha | = 2} a _ {\alpha} (x) \xi^ {\alpha} \neq 0, \tag {2.2}
$$

for any real $n$ -vector $\xi \neq 0$ . If the principal coefficients $a_{\alpha}(x)$ are bounded in $\Omega$ and

$$
- \sum_ {| \alpha | = 2} a _ {\alpha} (x) \xi^ {\alpha} \geq c _ {0} | \xi | ^ {2}, \tag {2.3}
$$

for all real $\xi$ and $x\in \Omega$ , where $c_{0} > 0$ is independent of $x\in \Omega$ , then the operator (2.1) is said to be uniformly strongly elliptic in $\Omega$ .

The Laplace operator

$$
\Delta = \sum_ {i = 1} ^ {n} \frac {\partial^ {2}}{\partial x _ {i} ^ {2}}
$$

is clearly an elliptic operator. The operator $-\Delta$ is strongly elliptic.

DEFINITION 2.1. A linear operator $A$ in a Banach space $X$ is called a sectorial operator if it is a closed densely defined operator such that, for some $\phi$ in $(0, \pi/2)$ and some $M \geq 1$ and real $a$ , the sector

$$
S _ {a, \phi} = \{\lambda | \phi \leq | \arg (\lambda - a) | \leq \pi , \lambda \neq a \}
$$

is in the resolvent set of $A$ and

$$
\| (\lambda - A) ^ {- 1} \| \leq \frac {M}{| \lambda - a |} \quad \text { for   all } \quad \lambda \in S _ {a, \phi}.
$$

The Banach space $X$ in the above definition is usually chosen as a Sobolev space defined in the following.

For any non-negative integer j and a real number $p, 1 \leq p < \infty$ , define

$$
| u | _ {j, p} ^ {\Omega} = \left\{\sum_ {| \alpha | \leq j} \int_ {\Omega} | D ^ {\alpha} u | ^ {p} d x \right\} ^ {1 / p}, \tag {2.4}
$$

and for $p = +\infty$ , define
