# Multi-point maximum principles and eigenvalue estimates

Ben Andrews

Abstract Estimates on modulus of continuity, isoperimetric profiles of various kinds, and quantities involving function values at several points have been central in several recent results in geometric analysis. In these lectures I will focus mostly on the applications to partial differential equations, and to estimates on eigenvalues. These lectures were presented at the MATRIX program on “Recent trends on Nonlinear PDE of Elliptic and Parabolic type” at Creswick, November 5-16, 2018.

Acknowledgements This survey describes work supported by Discovery Projects grants DP0985802, DP120102462, and DP120100097, and Laureate Fellowship FL150100126 of the Australian Research Council.

# Introductory comments

In this article I want to describe some techniques which have been applied with some success recently to a variety of problems, ranging from my proof with Julie Clutterbuck of the sharp lower bound on the fundamental gap for Schrodinger operators ¨ [4] to Brendle’s proof of the Lawson conjecture [14] and my proof with Haizhong Li of the Pinkall-Sterling conjecture [7]. I will discuss several other interesting applications below. The common thread in these techniques is the application of the maximum principle to functions involving several points or to functions depending on the global structure of solutions. Further related ideas, and more details on some of the methods presented here, can be found in the author’s survey article [1].

Ben Andrews

Mathematical Sciences Institute, Australia National University, e-mail: Ben.Andrews@anu.edu.au

# Lecture 1: Controlling the modulus of continuity in heat equations

# 1.1 Moduli of continuity

Today I want to discuss how two-point maximum principles can be used to control the modulus of continuity for solutions of heat equations. This implies a lot of information including sharp gradient estimates. In particular the modulus of continuity estimates imply sharp decay estimates, which are the key to some sharp eigenvalue inequalities, the first of which we will reach by the end of today’s lecture.

Recall that for a function f (on a metric space), a function  of one positive variable is a modulus of continuity for $f \operatorname { i f } \omega ( s )$ bounds the difference in function values $\left| f ( y ) - f ( x ) \right|$ for all point with separation $d ( x , y ) = s .$ .

I will adopt a slightly different definition, for the sake of simplicity further down the track: We say  is a modulus of continuity for $f \operatorname { i f }$

$$
\frac {| f (y) - f (x) |}{2} \leq \omega \left(\frac {d (x , y)}{2}\right)
$$

for all x and y. This differs from the usual definition by the factors of $^ { 2 , }$ and the reason for these will become clear in a moment. For a time-dependent function $f ( x , t )$ , we say that a time-dependent function $\omega ( s , t )$ is a modulus of continuity for f if $\omega ( . , t )$ is a modulus of continuity for $f ( . , t )$ for each t, which means that

$$
\frac {| f (y , t) - f (x , t) |}{2} \leq \omega \left(\frac {d (x , y)}{2}, t\right)
$$

for all x and y and all t. In particular, there is a smallest modulus of continuity (which we will sometimes call ‘the modulus of continuity of $f ^ { \prime } )$ defined by

$$
\omega_ {f} (s, t) = \sup \left\{\frac {| f (y) - f (x) |}{2}: \frac {d (x , y)}{2} = s \right\}.
$$

The following example is an important one:

Lemma 1. Suppose that f is a function on the real line which is odd, increasing, and concave on the positive half-line. Then

$$
\omega_ {f} (s) = f (s)
$$

$f o r s > 0 .$

Proof. We will show that for any fixed $s > 0 ,$ , the supremum of $\left| f ( y ) - f ( x ) \right|$ among points with $| y - x | = 2 s$ is attained at the points $y = s , x = - s ,$ , so that $\omega _ { f } ( s ) = $ ${ \frac { f ( s ) - f ( - s ) } { \gamma } } = f ( s )$ since $f$ is odd. First, we can assume that $y > x$ and $f ( y ) - f ( x ) =$ $\left| f ( y ) - f ( x ) \right|$ | since $f$ is increasing. Then the function $\eta ( x ) = f ( x + s ) - f ( x - s )$ is even in x since f is odd, and we have for $x \geq s$ that

$$
x - s = \frac {2 s}{x + s} (0) + \frac {x - s}{x + s} (x + s); \quad s = \frac {x}{x + s} (0) + \frac {s}{x + s} (x + s),
$$

so since f is concave on $[ 0 , x + s ]$ and $f ( 0 ) = 0$ we have

$$
f (x - s) \geq \frac {x - s}{x + s} f (x + s); \quad f (s) \geq \frac {s}{x + s} f (x + s); \quad \Longrightarrow f (x - s) + 2 f (s) \geq f (x + s)
$$

which is equivalent to

$$
\eta (x) - \eta (0) = f (x + s) - f (x - s) - f (s) + f (- s) = f (x + s) - f (x - s) - 2 f (s) \leq 0.
$$

If $0 < x < s$ then we have

$$
\eta (x) - \eta (0) = f (x + s) - f (x - s) - 2 f (s) = f (x + s) + f (s - x) - 2 f (s) \leq 0
$$

since $f$ is concave on the interval $[ s - x , s + x ] \subset \mathbb { R } _ { + }$ . Thus 0 is the global maximum of , as claimed.

We observe that if $f _ { 0 }$ is an odd, increasing function which is concave for positive values, then the same remains true for $f ( . , t )$ for each $t > 0 \mathrm { i f } f$ satisfies the heat equation

$$
\frac {\partial f}{\partial t} = \frac {\partial^ {2} f}{\partial s ^ {2}}. \tag {1}
$$

Thus we have the following curious corollary:

Corollary 1. $I f f _ { 0 }$ is an odd, increasing function which is concave for positive values, then $\omega _ { f } ( s , t ) = f ( s , t )$ for all $s > 0$ and $t > 0 \ i f f$ evolves by (1). In particular, the modulus of continuity of f satisfies the one-dimensional heat equation.

Furthermore, if u is a solution of the heat equation

$$
\frac {\partial}{\partial t} u = \Delta u := \sum_ {i = 1} ^ {n} \frac {\partial^ {2} u}{\partial x _ {i} ^ {2}} \tag {2}
$$

on $\mathbb { R } ^ { n }$ which depends on only one of the spatial variables, so that $u ( x _ { 1 } , \cdots , x _ { n } , t ) =$ $f ( x _ { 1 } , t )$ , where f is as above, then $\omega _ { u } ( s , t ) = f ( s , t )$ , and $\omega _ { u }$ is a solution of the one-dimensional heat equation.

Later we will see this as the extreme case of a result for general solutions of heat equations.

# 1.2 Motivation: Zero counting for equations in one space variable

For equations in one spatial variable, we can use zero-counting methods to get a good understanding of how the modulus of continuity of a solution of the heat equation changes with time. This is based on the fact that the number of zeroes of a solution, or the number of intersections of two solutions, does not increase in time — a result first observed by Sturm in 1836 for solutions of the linear heat equation, and refined into a very general tool more recently, particularly through work of Hiroshi Matano, Sigurd Angenent and others. Roughly speaking, as long as new zeroes (or intersections) are not introduced on the boundary or at infinity, then new ones cannot appear. It is also true that the number strictly decreases whenever a zero (or intersection) becomes degenerate in the sense that the first derivative also vanishes, but we will not need this fact.

Consider a bounded smooth solution u : $\mathbb { R } \times \mathbb { R } _ { + } \to [ - M , M ]$ of the heat equation on the real line. We will use the zero-counting argument to compare u with the special solution of (1) with the same range $[ - M , M ]$ given by $\scriptstyle \varphi ( x , t ) = M \operatorname { e r f } \left( { \frac { x - a } { \sqrt { 2 t } } } \right)$ for any $a \in \mathbb { R }$ . Since u is smooth and $\varphi ( . , t )$ approaches a Heaviside function as $t $ 0, for any $\varepsilon > 0 .$ , we have exactly one intersection between ${ \bigl ( } 1 + \varepsilon { \bigr ) } \varphi ( , t )$ and $u ( . , t )$ for $t > 0$ sufficiently small. Since the number of intersections does not increase with time (noting that $( 1 + \varepsilon ) \varphi \to ( 1 + \varepsilon ) M > u \mathrm { a s } s \to $ ∞ and $( 1 + \varepsilon ) \varphi \to - ( 1 + \varepsilon ) M < u$ as $s \to - \infty$ , so no new zeroes are produced near infinity), we have at most one intersection between $\left( 1 + \varepsilon \right) \varphi ( . , t )$ and $u ( . , t )$ for every $t > 0 ;$ on the other hand the asymptotics of  near $s = \pm \infty$ also imply that there is at least one intersection, by the intermediate value theorem. Therefore we have exactly one intersection between $\left( 1 + \varepsilon \right) \varphi ( . , t )$ and $u ( . , t )$ for each $t > 0$ .

For any given $x \in$ R and $t > 0$ , there is a unique $a \in$ R such that $( 1 + \varepsilon ) \varphi ( x , t ) =$ $u ( x , t )$ . Since there is only one intersection between $u \big ( . , t \big )$ and $\displaystyle ( 1 + \varepsilon ) \varphi ( . , t )$ , and since $( 1 + \varepsilon ) \varphi ( s , t ) > u ( s , t )$ ) for large s, we have $u ( x + s , t ) < ( 1 + \varepsilon ) \varphi ( x + s , t )$ for $s > 0 .$ , and $u ( x + s , t ) > ( 1 + \varepsilon ) \varphi ( x + s , t )$ for $s < 0$ . This implies

$$
| u (x + s, t) - u (x, t) | \leq (1 + \varepsilon) | \varphi (x + s, t) - \varphi (x, t) | \leq 2 (1 + \varepsilon) \varphi \left(\frac {s}{2}, t\right)
$$

by Lemma 1, since  is odd, increasing, and concave for positive values. We conclude that $\omega _ { u } ( s , t ) \leq ( 1 + \varepsilon ) \varphi ( s , t )$ . Finally, letting $\varepsilon \to 0$ we deduce that $\omega _ { u } \leq \varphi$ . This gives a universal bound on the modulus of continuity for solutions of the heat equation, depending only on M. Notice that this result is sharp, since equality holds in the particular case where $u = \varphi$ .

From the modulus of continuity estimate, we can also deduce a sharp gradient estimate: Taking $y  x .$ , we conclude that $\begin{array} { r } { | u ^ { \prime } ( x , t ) | \leq \varphi ^ { \prime } ( 0 , t ) = \frac { M } { \sqrt { \pi t } } . \mathrm { ~ A g a i n } } \end{array}$ = √M . Again, this is sharp because equality holds on the solution .

We remark that this argument is very robust, and applies equally well for solutions of other parabolic equations such as the p-Laplacian heat flows and graphical curve shortening flow. In fact, interpreted in the right way, this idea gives sharp estimates for arbitrary parabolic equations in one dimension, by comparison to solutions which approach a Heaviside function at the initial time.

Unfortunately there is no good analogue of the zero-counting argument known in higher dimensions, so we must find other ways to control the modulus of continuity.

In fact the result we just obtained does have a direct analogue in higher dimensions, but to prove it we instead use a two-point maximum principle argument.
