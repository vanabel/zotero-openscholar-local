# INTEGRAL MAXIMUM PRINCIPLE AND ITS APPLICATIONS

Alexander Grigor’yan

Abstract.The integral maximum principle for the heat equation on a Riemannian manifold is improved and applied to obtain estimates of double integrals of the heat kernel.

# 1. Introduction and main results

In the present paper we develop a general approach to some estimates of solutions to heat equation bases on so-called integral maximum principle . Suppose that M is a smooth connected complete non-compact Riemannian manifold and consider some precompact subregion $\Omega \subset M$ . Suppose also that $\boldsymbol { u } ( \boldsymbol { x } , t )$ is a (weak) solution to Dirichlet mixed boundary value problem in a cylinder $\Omega \times ( 0 , T )$ :

$$
u _ {t} - \Delta u = 0, \quad u | _ {\partial \Omega \times (0, T)} = 0 \tag {1.1}
$$

As it follows from the maximum principle, the function

$$
\sup _ {x \in \Omega} | u (x, t) |
$$

is decreasing in t. Moreover, it is also well-known, the following integral

$$
\int_ {\Omega} u ^ {2} (x, t) d x
$$

is a decreasing function of t too. This fact can be regarded as an integral version of the usual maximum principle.

There is a further development of this idea which has been applied in a series of works to obtain heat kernel estimates (see , for example, $[ 1 ] , [ 3 ] , [ 7 ] , [ 5 ] )$ and consists of the fact that some weighted integral of $u ^ { 2 }$ decreases in t. Namely, this is applicable to the integral

$$
I (t) = \int_ {\Omega} u ^ {2} (x, t) e ^ {\xi} d x \tag {1.2}
$$

provided the function $\xi ( x , t )$ is locally Lipschitz and satisfies the relation

$$
\xi_ {t} + \frac {1}{2} | \nabla \xi | ^ {2} \leq 0. \tag {1.3}
$$

The simplest non-trivial examples of such functions $\xi$ are as follows:

$$
\xi = \frac {d (x) ^ {2}}{2 t}
$$

$d ( x )$ being a locally Lipschitz function such that $| \nabla d ( x ) | \le 1$ (for instance, a distance function from a set) and

$$
\xi = \alpha d (x) - \frac {\alpha^ {2}}{2} t
$$

α being an arbitrary constant.

The following improvement of the maximum principle is proved in Section 2 below.

Theorem 1 (Integral maximum principle) Suppose that $\boldsymbol { u } ( \boldsymbol { x } , t )$ is a (weak) solution to the mixed problem (1.1) and a locally Lipschitz function $\xi$ satisfies the relation (1.3) in $\Omega \times ( 0 , T )$ , then the function

$$
I (t) \exp (2 \lambda_ {1} (\Omega) t)
$$

is decreasing in $t \in ( 0 , T )$ where I(t) is defined by (1.2) and $\lambda _ { 1 } ( \Omega )$ is the first Dirichlet eigenvalue of Ω.

B.Davies [4] proved the following universal integral bound for the heat kernel $p ( x , y , t )$ being the smallest positive fundamental solution to the heat equation (for details of the definition of the heat kernel see [2] ). Let A and B be two Borel sets in M with finite volumes and let the distance $R = \operatorname { d i s t } ( A , B )$ be positive, then

$$
\int_ {A} \int_ {B} p (x, y, t) d x d y \leq \sqrt {\mu A \mu B} \exp \left(- \frac {R ^ {2}}{4 t}\right). \tag {1.4}
$$

This estimate is of much importance due to its generality: no a priori geometric assumption are needed for (1.4) to be valid. It turns out that Davies’s estimate can be deduced with ease from the integral maximum principle. Moreover, Theorem 1 implies the improved version of (1.4) :

Theorem 2 Let A, B be two Borel subsets in M of a finite volume and $R = \operatorname { d i s t } ( A , B )$ , then

$$
\int_ {A} \int_ {B} p (x, y, t) d x d y \leq \sqrt {\mu A \mu B} \exp \left(- \frac {R ^ {2}}{4 t} - \lambda_ {1} (M) t\right). \tag {1.5}
$$

Here $\lambda _ { 1 } ( M )$ is by definition the bottom of the spectrum of the Laplacian in $L ^ { 2 } ( M )$ that is called the spectral radius and coincides with inf $\lambda _ { 1 } ( \Omega )$ over all precompact subregions Ω.

If the spectral radius of a manifold is positive then the estimate of theorem 2 gives the sharp speed of decay of heat kernel as $t \to \infty$ because as it is known

$$
\lim _ {t \to \infty} \frac {\log p (x , y , t)}{t} = - \lambda_ {1} (M).
$$

Takeda [8] proved by a probabilistic method another kind of double integral estimate of heat kernel. Let A be an arbitrary compact of a positive volume on M and let us denote by $A ^ { R }$ the open R-neighbourhood of A where $R > 0$ . Let $X _ { t }$ be Brownian motion on manifold M governed by heat equation (1.1) . We shall consider the un-normalised law $\mathbf { P } _ { A }$ of $X _ { t }$ under the condition that the initial point $X _ { 0 }$ is uniformly distributed in A, where ”un-normalised” means that the maximum value of $\mathbf { P } _ { A }$ is equal to $\mu A$ rather than to 1. Takeda’s inequality for this setting estimates the probability $P ( R , T )$ for $X _ { t }$ to exit $A ^ { R }$ by a time $T$ starting at a point of A that is the function

$$
P (R, T) \equiv \mathbf {P} _ {A} \left(\exists t \leq T: X _ {t} \notin A ^ {R} \mid X _ {0} \in A\right).
$$

The following sharpened version of Takeda’s inequality is due to T.Lyons [6]

$$
P (R, T) \leq 1 6 \mu A ^ {R} \int_ {R} ^ {\infty} \frac {1}{(4 \pi T) ^ {\frac {1}{2}}} \exp (- \frac {\eta^ {2}}{4 T}) d \eta \tag {1.6}
$$

In Section 3 we obtain by means of the integral maximum principle an analytic proof of a similar inequality which however doesn’t cover (1.6) but sometimes is sharper.

Theorem 3 Let $\boldsymbol { u } ( \boldsymbol { x } , t )$ be a smooth subsolution to the heat equation in the cylinder $A ^ { R } \times [ 0 , T ]$ (where $A \subset M$ is a compact and $R , T$ are arbitrary positive numbers) i.e.

$$
u _ {t} - \Delta u \leq 0
$$

and suppose that

$$
0 \leq u (x, t) \leq 1 \quad a n d \quad u (x, 0) = 0 \quad \forall x \in A ^ {R}, t \in [ 0, T ], \tag {1.7}
$$

then

$$
\int_ {A} u ^ {2} (x, T) d x \leq \mu \left(A ^ {R} \setminus A\right) \max \left(\frac {R ^ {2}}{2 T}, \frac {2 T}{R ^ {2}}\right) \exp \left(- \frac {R ^ {2}}{2 T} + 1\right) \tag {1.8}
$$

To explain connection of this theorem with inequality (1.6) we first mention that the following function

$$
u (x, t) \equiv \mathbf {P} (\exists \tau \leq t: X _ {\tau} \notin A ^ {R} | X _ {0} = x)
$$

(where P denotes a probability measure) satisfies the heat equation in the cylinder in question and the conditions (1.7) . Thus, Theorem 3 is applicable to this function. Noting that the function $P ( R , T )$ is equal to $\textstyle \int _ { A } u ( x , T )$ dx and applying Cauchy-Schwarz inequality we get from (1.8)

$$
P (R, T) \leq \sqrt {\mu (A) \mu (A ^ {R} \setminus A)} \max \left(\frac {R}{\sqrt {2 T}}, \frac {\sqrt {2 T}}{R}\right) \exp (- \frac {R ^ {2}}{4 T} + \frac {1}{2}). \tag {1.9}
$$

Compare this inequality to that of (1.6) . It is easy to check that for all R, T the following estimate is valid

$$
\int_ {R} ^ {\infty} \exp (- \frac {\eta^ {2}}{4 T}) d \eta \leq \frac {2 T}{R} \exp (- \frac {R ^ {2}}{4 T})
$$

and, moreover, the ratio of the left and the right sides here tends to 1 as R2 $\begin{array} { r } { \frac { R ^ { 2 } } { T }  \infty } \end{array}$ . Therefore, (1.6) implies that

$$
P (R, T) \leq \frac {1 6}{\sqrt {\pi}} \mu (A ^ {R}) \frac {\sqrt {T}}{R} \exp (- \frac {R ^ {2}}{4 T}) \tag {1.10}
$$

and for large $\textstyle { \frac { R ^ { 2 } } { T } }$ this inequality is only a bit weaker than (1.6) . On the other hand for $\textstyle { \frac { R ^ { 2 } } { 2 T } } \geq 1 \ ( 1 . 9 )$ implies

$$
P (R, T) \leq \sqrt {\frac {e}{2}} \sqrt {\mu (A) \mu (A ^ {R} \setminus A)} \frac {R}{\sqrt {T}} \exp (- \frac {R ^ {2}}{4 T}) \tag {1.11}
$$

or, applying ${ \sqrt { a b } } \leq ( a + b ) / 2$ ,
