# CVRPTW mathematical model

This repository contains two implementations of the same operational problem. `app/milp.py` is an actual PuLP/CBC mixed-integer linear program. `app/routing.py` uses OR-Tools RoutingModel with capacity/time dimensions and guided local search; that path is a heuristic constraint-programming routing search, **not** a linear-programming solve or a certificate of global optimality.

## Sets and quantities

- Customers `C = {1,...,n}`, vehicles `K`, outbound depot `s`, distinct return depot `e` at the same geographic point.
- `d_ij`: nonnegative integer modeled distance in meters.
- `tau_ij = ceil(d_ij / speed_m_per_second)`.
- `q_i`: demand in integer kg; `Q_k`: vehicle capacity.
- `[a_i,b_i]`: permitted service-start window, inclusive; `h_i`: positive service duration.
- `S_k,E_k,H_k`: fixed shift start, latest return, maximum total working time.
- Cost coefficients use 10,000 integer cost units per currency unit. Fuel per modeled meter and wages per second are rounded to integer coefficients; fixed dispatch cost is rounded to integer units. The reported objective uses these same coefficients.

## Decision variables

`x_ijk` is binary: vehicle `k` travels directly from `i` to `j`. The allowed arc set has no incoming arcs to the outbound depot, no outgoing arcs from the return depot, no self-loops, and no direct empty start-to-end arc.

`u_k` is binary: dispatch vehicle `k`. `t_ik` is a continuous service-start time in seconds for node `i`, vehicle `k`, bounded between 0 and 86,400. Define `y_ik = sum_j x_ijk`, the indicator that vehicle `k` serves customer `i`.

## Objective

Minimize

\[
\sum_{k\in K}\left[f_k u_k + c_k\sum_{(i,j)} d_{ij}x_{ijk} + w_k(t_{ek}-S_k)\right].
\]

Working time includes travel, customer service, and waiting, from the fixed shift start to return. Unused vehicles have `t_ek = S_k` and incur zero cost. The engine does not delay the driver clock to reduce paid waiting.

## Constraints

Each customer is served once:

\[
\sum_{k\in K} y_{ik}=1,\qquad i\in C.
\]

Depot departure/return and customer flow:

\[
\sum_{j\in C}x_{sjk}=u_k,\quad \sum_{i\in C}x_{iek}=u_k,
\]

\[
\sum_j x_{jik}=\sum_j x_{ijk}=y_{ik},\quad y_{ik}\le u_k.
\]

Vehicle capacity:

\[
\sum_{i\in C} q_i y_{ik}\le Q_k.
\]

Time propagation and service windows:

\[
t_{jk}\ge t_{ik}+h_i+\tau_{ij}-M(1-x_{ijk}),
\]

\[
a_i-M(1-y_{ik})\le t_{ik}\le b_i+M(1-y_{ik}).
\]

Shift constraints:

\[
t_{sk}=S_k,\quad S_k\le t_{ek}\le S_k+u_k\min(E_k-S_k,H_k).
\]

The code uses `M = 2,000,000` seconds, safely above twice the modeled one-day horizon for admissible arcs. Any arc requiring more than one day of transit/service is explicitly forbidden. Positive service times make time-propagation constraints rule out disconnected customer cycles, including co-located stops; no route can advance around a positive-duration cycle and return to its original time.

## Feasibility and solver status

Early physical arrival is permitted; service waits until the delivery window opens. Service must **start** by the window end; it may finish later. Return to the depot must meet both the shift-end and total-work constraints. Every order is mandatory; no penalty-based dropping is enabled.

CBC reports `OPTIMAL_MILP` only when PuLP's solution status indicates a proven optimum. A time-limited integer incumbent is `FEASIBLE_MILP`, even if PuLP's generic status string says Optimal. OR-Tools returns `FEASIBLE_HEURISTIC` with `optimality_proven=false`. Failure to find a routing solution within the time limit is not proof of infeasibility. An infeasible CBC model can be labeled `PROVEN_INFEASIBLE`.

Every solution is converted to earliest-feasible service schedules and independently reconstructed from order sequences. Capacity, service-start windows, return/working-time bounds, exactly-once coverage, driver assignment, distance, reported schedules, and the discrete objective are verified before storage. This validates constraints and reporting, not global optimality.

The MILP mode is limited to 12 customers and 5 vehicles because binary arc counts grow quadratically with customers and linearly with fleet size; OR-Tools mode supports up to 200 customers / 30 vehicles in the API. Those are input limits, not claims that every instance within them can be solved in 30 seconds.
