"""Numerical semantic oracle for the declared forward block, not timing.

Double precision isolates graph/partition errors from device rounding. The
reference dense calculation assembles full weight matrices independently of
the DAG's tensor-parallel operator sequence.
"""
import math
import numpy as np

from wafer_sim.workloads.spatial import validate


def norm(x, gamma, beta, epsilon=1e-5):
    centered = x-x.mean(axis=-1, keepdims=True)
    return centered/np.sqrt((centered*centered).mean(axis=-1, keepdims=True)+epsilon)*gamma+beta


def softmax(x):
    e = np.exp(x-x.max(axis=-1, keepdims=True))
    return e/e.sum(axis=-1, keepdims=True)


def gelu(x):
    return 0.5*x*(1+np.vectorize(math.erf)(x/math.sqrt(2)))


def initial_values(block):
    rng = np.random.default_rng(17)
    values = {}
    for d in block.workload.data:
        if d.producer is not None:
            continue
        values[d.id] = rng.normal(0, 0.1, block.tensors[d.id]["shape"])
    for r in range(1, block.dimensions["shards"]):
        for suffix in ("input", "ln1:gamma", "ln1:beta", "ln2:gamma", "ln2:beta"):
            values[f"r{r}/{suffix}"] = values[f"r0/{suffix}"].copy()
    return values


def evaluate_graph(block, values):
    values = dict(values)
    graph = validate(block.workload)
    for name in graph.order:
        op, spec = graph.operations[name], block.operators[name]
        inputs = [values[d] for d in op.inputs]
        kind = spec["kind"]
        if kind == "layer_norm":
            output = norm(*inputs, epsilon=spec["epsilon"])
        elif kind == "linear":
            output = inputs[0] @ inputs[1]
        elif kind == "attention_scores":
            b,s,_ = inputs[0].shape
            q,k = (x.reshape(b,s,spec["heads"],spec["head_dim"]).transpose(0,2,1,3)
                   for x in inputs)
            output = q @ k.swapaxes(-1,-2)
        elif kind == "scaled_softmax":
            output = softmax(inputs[0]/math.sqrt(spec["head_dim"]))
        elif kind == "attention_values":
            probability,v = inputs
            b,s,_ = v.shape
            v = v.reshape(b,s,spec["heads"],spec["head_dim"]).transpose(0,2,1,3)
            output = (probability @ v).transpose(0,2,1,3).reshape(b,s,-1)
        elif kind in {"add", "sum_allreduce"}:
            output = sum(inputs)
        elif kind == "gelu_erf":
            output = gelu(inputs[0])
        else:
            raise AssertionError(f"Unverified operator: {kind}")
        for d in op.outputs:
            if output.shape != block.tensors[d]["shape"]:
                raise AssertionError(f"Incorrect tensor shape: {d}")
            values[d] = output.copy()
    return values


def dense_forward(block, values):
    dims = block.dimensions
    b,s,h,heads,p = (dims[k] for k in ("batch","sequence","hidden","heads","shards"))
    x = values["r0/input"]
    z = norm(x, values["r0/ln1:gamma"], values["r0/ln1:beta"])
    full_weights = {kind: np.concatenate([values[f"r{r}/w{kind}"] for r in range(p)],axis=1)
                    for kind in ("q","k","v","up")}
    q,k,v = ((z @ full_weights[kind]).reshape(b,s,heads,h//heads).transpose(0,2,1,3)
             for kind in ("q","k","v"))
    attention = softmax((q @ k.swapaxes(-1,-2))/math.sqrt(h//heads)) @ v
    context = attention.transpose(0,2,1,3).reshape(b,s,h)
    wo = np.concatenate([values[f"r{r}/wo"] for r in range(p)],axis=0)
    residual = x+context @ wo
    z = norm(residual, values["r0/ln2:gamma"], values["r0/ln2:beta"])
    wd = np.concatenate([values[f"r{r}/wdown"] for r in range(p)],axis=0)
    return residual+gelu(z @ full_weights["up"]) @ wd
