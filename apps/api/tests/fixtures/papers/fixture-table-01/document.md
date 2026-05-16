cells. A standard professional reference for this material is Feller (1971). 
Table 1 lists the forms that have been found with a reasonably convenient al­
gebraic form, with the available rescaling options in the top line. Form 1 is the 
trivial special case of a distribution F of rigidly constant density. Form 2 is a basic 
Poisson distribution in which "atoms" of fixed (unit) flux are placed randomly 
in x. Form 3 is a Poisson variant in which the atoms have an exponential distribu­
tion of flux. Form 4 generalises the Poisson variant 3 to a model in which atoms 
have m ~ 1 exponentially-distributed components (oF m is a hypergeometric func­
tion). Form 5 is a Gamma distribution, particularly popular among statisticians. 
Form 6 arises in the study of random walks on an integer lattice. Form 7 is known 
as the Levy distribution. L being a simple power law, form 7 has the "stable" 
property (Lukacs, 1970) that self-convolution recovers the same shape. Form 8 
is another stable distribution, apparently overlooked previously. Perhaps under­
standably, form 9 also appears to be absent from the literature (1) is the parabolic 
cylinder function). Forms 10 to 13 are combinations of the above that happen to 
have closed form, 11 being a special case of 10. Of these, only the Poisson forms 
2, 3 and 4 have the infinitesimal interpretation (15) with integrable A. 
The basic Poisson form 2 is, in fact, the original "monkey model" without any 
large-n approximation. However, it restricts all fluxes to integer multiples of some

## Page 15

6 JOHN SKILLING 
Table 1 
Analytic Levy-Khinchin Representations 
L(F) Pr(Fla) = P(F) 
L(f3F)e--yF P(f3F) e--yF / Jooo P(f3F) e--yF dF 
1 a6(F) 6(F - a) 
2 a6(F - 1) e- a L:oo an 6(F - n) n=O n! 
3 aFe- F e- a (6(F) +e- F ~lt (2v'QF)) 
4 aF'"'e- F e-a(6(F) + aF",-le- F of (m±1 m±2 ... 2' aF"')) (m I)! (m-l)! m m' m' " mfn. 
5 ae- F F-1+"'e- F 
l'{a) 
6 a1o(F)e- F !j;Ia(F) e- F 
7 a F-1/2 
~ 
a e-:a2/4F 2:.;;Fa 
8 aPJi,3)F-I/3 
2 311' a 3/ 2 (~ 311'Fs/2 K! 2 a 27F 
9 ae F erfc( v'F) ..jI a (2F)a-l eF/ 2 V-2 a-l (&) 
10 ae- aF + f3e- bF a"'bil F- 1±a±.8 e- bF M (a· a + f3' (b - a)F) P(a±.8) " 
11 ae- aF + ae- bF ( r-1/ 2 () .fit''t ~ e-(a±b)F/2 I 1 b-a F Pa b-a a-]j" 2 
12 ae- F + f3Fe- F ( ) (a-l)/2 
~ C.8- F Ia-l (2JiF) 
13 ae- F + f3e- F /.;;iF 2'" F-l±a e2.8-F-.82/2F VI 2 (f3V2fF) 7J; - a 
unit quantum, whereas we usually require flux to be on a continuous scale. To 
allow individual fluxes to be continuous, the natural prior distribution for a single 
atom is exponential 
(17) 
because that is the PME assignment appropriate to a constraint q on the expected 
flux. This yields the Poisson variant form 3, now seen to be the natural prior 
distribution for a measure F. It has two hyper-parameters, q for the quantum 
size, and the Poisson mean number of atoms per unit range x (which could be a 
function of x). The associated macroscopic distribution over a range on which a

## Page 16

MASSIVE INFERENCE AND MAXIMUM ENTROPY 7 
atoms are expected is 
Pr(Fla,q) = e- a (8(F) +e-F/q~It{2JaF/q)) (18) 
Interestingly, the delta function ensures that the posterior mode follows the prior 
mode at F = 0: unless the data utterly prohibit it, the most probable individual 
measure F will be null. This destroys the supposition of QME that the maximum 
might be a useful selection from the posterior distribution. Instead, the mean of 
the posterior is used for display purposes. Of itself, the mean lacks the symmetry 
properties that underlie a MaxEnt selection, but it is a sufficient statistic for 
reading off the mean value of any integral property of f. To determine deeper 
information such as uncertainty, the posterior distribution must be recorded more 
fully, usually as a set ofrandom samples. 
Because the flux in any sample is located as a set of "point mass" delta func­
tions, we call (17)/(18) the "Massive Inference" (MassInf) prior. Computationally, 
the MassInf prior is convenient because each sample of F is fully defined by a 
finite number of atoms, whilst other forms have flux (mostly very small) every­
where. Also, the exponential prior on each atomic flux is conjugate to the Gaussian 
likelihood function that is commonly appropriate, so it can be folded in without 
un-necessary algorithmic complexity. 
5. Masslnf Pixellation 
By construction, MassInf has no difficulty with pixellation. Any finite resolution 
with a restricted number of cells may damage the results, but inferences will have a 
well-defined continuum limit as the resolution increases. This is confirmed with the 
example (9) above, for which the upper curve in Fig. 1 shows the prior predictive 
"evidence" values for various numbers of cells. As it ought, this increases gently 
towards the continuum limit, as opposed to the awkward behaviour of QME. 
Towards this limit, the posterior behaves sensibly. 
6. Masslnf Polarization 
Even if an image has the extra complication of polarization, we can still model 
it with a Poisson distribution of point atoms, in the spirit of the original mon­
key model. Instead of simply assigning an exponential prior on a single intensity, 
though, an atom now has polarized structure on which a prior is needed. 
Among the oscillating electric fields Ez and E1I comprising a beam of radiation 
along z, there can be up to four different correlation coefficients among the in­
phase and out-of-phase components. These define four Stokes' parameters I, Q, 
U, V (Stone, 1963). Of these, I is the (non-negative) total intensity. The other 
three are smaller and obey 
(19) 
Geometrically, they lie within the "Poincare sphere" of radius 1. They can be 
rotated into each other by harmless coordinate rotation and time offsets, so we

## Page 17

8 JOHN SKILLING 
o 10 20 30 40 
M = number of cells 
Figure 1. Test comparison of MaxEnt and MassInf "evidence" values (hyper-parameters being 
given their optimal values). 
should assign the prior uniformly over the sphere. 
Pr(I,Q,U, V 11 atom) = B(I,P) (20) 
Let us restrict our attention to the special case U = V = O. The polarization 
state now has two channels, linear x with intensity X = HI + Q), and linear y 
with intensity Y = HI - Q). These states being orthogonal, it is natural to assign 
exponential priors Pr(X) = e- x and PreY) = e- Y to each as in (17), scaling to 
q = 1 for convenience. In terms of I and Q, this sets 
Pr(I,Q I U = V = 0, 1 atom) = e- I /2, IQI ~I 
This implies that B(I, P) ()( e-I • After normalising to unit total, we reach 
{ e- I /87r, P < I } Pr(I,Q,U, VII atom) = 0 th - . , 0 erWlse 
With the general prior in hand, we can now investigate special cases. 
1. Fixed polarization state: Q/I, U/I, V/I all known. 
Pr(I I fixed polarization, 1 atom) = e-I 
Lacking any sub-structure, the atom has a simple exponential prior. 
(21) 
(22) 
(23) 
2. Observe linear polarizations from arbitrarily polarized radiation: seek X 
and Y after marginalizing over U and V. 
Pr(X 11 atom) = Xe- x and independently PreY 11 atom) = Ye- Y 
(24)

## Page 18

MASSIVE INFERENCE AND MAXIMUM ENTROPY 9 
Each of X and Y show the effect of internal structure, as if each was the con­
volution of two independent exponentially-distributed fluxes. The corresponding 
macroscopic prior can be found by setting m = 2 in form 4 of Table 1. 
3. Observe the total intensity from arbitrarily polarized radiation: seek I after 
marginalizing over Q, U and V. 
Pr(I 11 atom) = I 3 e- I /6 (25) 
The intensity appears as if it were the convolution of four independent exponentially­
distributed fluxes, though these cannot be identified individually among the four 
polarization parameters. The corresponding macroscopic prior can be found by 
setting m = 4 in form 4 of Table 1. 
7. Examples 
We present a simulation and an application to practical data. The simulation is 
due to Bretthorst (1990) and represents data 
D t = 100e- o.o3t + 50e- O•05t + et, t = 1,2, ... , 100 (26) 
where e is unit normally distributed noise. These data (Fig. 2) are to be analyzed 
to recover the spectrum I(x) of decay rates. 
2.0
