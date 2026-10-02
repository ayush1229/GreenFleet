"""Seeded bounded bit-amplitude search; no quantum hardware or speedup claim."""
from dataclasses import dataclass
from time import perf_counter
from typing import Callable
import numpy as np
from .contracts import Record


@dataclass(frozen=True)
class SearchProblem:
    n_bits: int
    evaluate: Callable
    multiobjective: bool = False
    on_generation: Callable | None = None


@dataclass(frozen=True)
class SearchTrace(Record):
    best_bits: tuple[int, ...]
    best_fitness: object
    samples: tuple[tuple[int, ...], ...]
    probabilities: tuple[tuple[float, ...], ...]
    evaluations: int
    resets: int
    generations: tuple[dict, ...]


def rank_population(fitness):
    """Feasibility-first nondomination, normalized crowding, deterministic ties."""
    from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
    values=np.asarray(fitness,dtype=float)
    feasible=np.where(values[:,0]<=0)[0]
    order=[]
    if len(feasible):
        fronts=NonDominatedSorting().do(values[feasible,1:])
        for front in fronts:
            indices=feasible[front]
            crowd=np.zeros(len(indices))
            for axis in range(1,values.shape[1]):
                sorted_idx=np.argsort(values[indices,axis],kind="stable")
                span=np.ptp(values[indices,axis])
                if span==0:
                    continue
                crowd[sorted_idx[0]]=crowd[sorted_idx[-1]]=np.inf
                for k in range(1,len(indices)-1):
                    crowd[sorted_idx[k]]+=(values[indices[sorted_idx[k+1]],axis]-values[indices[sorted_idx[k-1]],axis])/span
            order.extend(sorted(indices.tolist(),key=lambda i:(-crowd[np.where(indices==i)[0][0]],i)))
    order.extend(sorted(np.where(values[:,0]>0)[0].tolist(),key=lambda i:(values[i,0],tuple(values[i,1:]),i)))
    return order


def qie_search(problem,config):
    if problem.n_bits<1:
        raise ValueError("QIE needs at least one bit")
    rng=np.random.default_rng(config.seed)
    theta=np.full(problem.n_bits,np.pi/4)
    samples=[];probabilities=[];logs=[];resets=0
    best_bits=None;best_fitness=None
    start=perf_counter();generation=0
    while len(samples)<config.budget:
        if config.timeout_s is not None and perf_counter()-start>=config.timeout_s:
            break
        p=np.sin(theta)**2
        batch=[];fitness=[]
        for _ in range(min(config.population_size,config.budget-len(samples))):
            bits=(rng.random(problem.n_bits)<p).astype(int)
            score=problem.evaluate(bits)
            sample=tuple(int(x) for x in bits)
            samples.append(sample);batch.append(bits);fitness.append(score)
        order=rank_population(fitness) if problem.multiobjective else sorted(range(len(fitness)),key=lambda i:(fitness[i],i))
        elite=batch[order[0]];elite_fitness=fitness[order[0]]
        if best_bits is None or (rank_population([best_fitness,elite_fitness])[0]==1 if problem.multiobjective else elite_fitness<best_fitness):
            best_bits=tuple(int(x) for x in elite);best_fitness=elite_fitness
        # Rotate only bits where a sampled non-elite disagrees with the chosen elite.
        disagreement=np.mean(np.array(batch)!=elite,axis=0)
        theta+=config.rotation*(2*elite-1)*disagreement
        theta=np.clip(theta,config.epsilon,np.pi/2-config.epsilon)
        generation+=1
        if generation%config.reset_interval==0 and config.reset_fraction>0:
            indices=rng.choice(problem.n_bits,max(1,int(problem.n_bits*config.reset_fraction)),replace=False)
            theta[indices]=np.pi/4;resets+=len(indices)
        probabilities.append(tuple(float(x) for x in np.sin(theta)**2))
        logs.append({"generation":generation,"evaluations":len(samples),"elite_fitness":elite_fitness,"elapsed_s":perf_counter()-start})
        if problem.on_generation:
            problem.on_generation({**logs[-1],"probability_min":float(np.min(np.sin(theta)**2)),"probability_max":float(np.max(np.sin(theta)**2)),"resets":resets})
    return SearchTrace(best_bits or (),best_fitness,tuple(samples),tuple(probabilities),len(samples),resets,tuple(logs))
