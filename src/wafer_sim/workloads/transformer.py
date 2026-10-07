"""A complete, declared tensor-parallel Transformer block forward pass.

Bias-free pre-LayerNorm, dense unmasked attention, exact-erf GELU, no dropout.
This is an analytical model, not recovered Llama work or a training step.
Logical worker ownership is independent of physical reticle placement.
"""
from dataclasses import dataclass
from math import prod

from wafer_sim.workloads.spatial import DataObject, Operation, Workload, natural, validate

PROVENANCE = "Declared float32 pre-LN Transformer block forward v1"


@dataclass(frozen=True)
class Block:
    workload: Workload
    tensors: dict
    operators: dict
    operation_workers: dict
    data_workers: dict
    collectives: tuple
    dimensions: dict


def build_block(*, batch, sequence, hidden, heads, ffn_hidden, shards):
    dims = dict(batch=batch, sequence=sequence, hidden=hidden, heads=heads,
                ffn_hidden=ffn_hidden, shards=shards)
    for key, value in dims.items():
        natural(value, key, positive=True)
    if shards < 2 or hidden % heads or heads % shards or ffn_hidden % shards:
        raise ValueError("Require >=2 shards, whole attention heads and whole FFN shards")
    b, s, h, f, p = batch, sequence, hidden, ffn_hidden, shards
    width, hp, dh, fp = h//p, heads//p, h//heads, f//p
    rows, elements = b*s, b*s*h
    data, operations, tensors, operators = [], [], {}, {}
    operation_workers, data_workers, collectives = {}, {}, []

    def tensor(name, shape, worker, producer=None, retain=False, role="activation"):
        shape = tuple(shape)
        tensors[name] = dict(shape=shape, dtype="float32", element_bytes=4, role=role)
        data_workers[name] = worker
        data.append(DataObject(name, 4*prod(shape), producer, retain, PROVENANCE))
        return name

    def operation(name, worker, kind, inputs, outputs, work, scratch=0, **attributes):
        operations.append(Operation(name, tuple(inputs), tuple(outputs),
                                    tuple((u, n) for u, n in work.items() if n),
                                    scratch, (), PROVENANCE))
        operation_workers[name] = worker
        operators[name] = dict(kind=kind, **attributes)

    def local(name, worker, kind, inputs, shape, work, scratch=0, retain=False, **attributes):
        output = tensor(f"{name}:out", shape, worker, name, retain)
        operation(name, worker, kind, inputs, (output,), work, scratch, **attributes)
        return output

    def parameter(name, shape, worker):
        return tensor(name, shape, worker, retain=True, role="parameter")

    def norm(prefix, worker, x):
        gamma = parameter(f"{prefix}:gamma", (h,), worker)
        beta = parameter(f"{prefix}:beta", (h,), worker)
        # Mean; centered variance; epsilon/rsqrt; normalize and affine.
        return local(prefix, worker, "layer_norm", (x, gamma, beta), (b,s,h),
            dict(scalar_add=4*elements-rows, scalar_mul=3*elements+2*rows,
                 scalar_rsqrt=rows), scratch=2*rows*4, epsilon=1e-5)

    def sum_allreduce(name, inputs):
        outputs = tuple(tensor(f"r{r}/{name}:out", (b,s,h), r, name) for r in range(p))
        operation(name, 0, "sum_allreduce", inputs, outputs,
                  dict(scalar_add=elements*(p-1)))
        collectives.append(dict(operation=name, participants=list(range(p)), root=0,
            input_objects=list(inputs), output_objects=list(outputs), elements=elements,
            element_bytes=4, reduction="sum", algorithm="root gather, sum, broadcast",
            completion="all output homes written before any dependent operation"))
        return outputs

    originals, attention_partials = [], []
    for r in range(p):
        prefix = f"r{r}"
        x = tensor(f"{prefix}/input", (b,s,h), r, role="replicated_input")
        originals.append(x)
        normalized = norm(f"{prefix}/ln1", r, x)
        qkv = []
        for kind in ("q", "k", "v"):
            weight = parameter(f"{prefix}/w{kind}", (h,width), r)
            qkv.append(local(f"{prefix}/{kind}", r, "linear", (normalized,weight),
                             (b,s,width), dict(mac=rows*h*width)))
        q,k,v = qkv
        scores = local(f"{prefix}/scores", r, "attention_scores", (q,k),
            (b,hp,s,s), dict(mac=b*s*s*width), heads=hp, head_dim=dh)
        attention_rows, attention_elements = b*hp*s, b*hp*s*s
        probabilities = local(f"{prefix}/softmax", r, "scaled_softmax", (scores,),
            (b,hp,s,s), dict(scalar_mul=attention_elements,
                scalar_max=attention_rows*(s-1),
                scalar_add=attention_elements+attention_rows*(s-1),
                scalar_exp=attention_elements, scalar_div=attention_elements),
            scratch=2*attention_rows*4, head_dim=dh)
        context = local(f"{prefix}/context", r, "attention_values", (probabilities,v),
            (b,s,width), dict(mac=b*s*s*width), heads=hp, head_dim=dh)
        weight = parameter(f"{prefix}/wo", (width,h), r)
        attention_partials.append(local(f"{prefix}/attention_out", r, "linear", (context,weight),
            (b,s,h), dict(mac=rows*width*h)))
    attention_results = sum_allreduce("attention_sum", attention_partials)
    residuals, ffn_partials = [], []
    for r in range(p):
        prefix = f"r{r}"
        residual = local(f"{prefix}/attention_residual", r, "add",
            (originals[r],attention_results[r]), (b,s,h), dict(scalar_add=elements))
        residuals.append(residual)
        normalized = norm(f"{prefix}/ln2", r, residual)
        weight = parameter(f"{prefix}/wup", (h,fp), r)
        up = local(f"{prefix}/ffn_up", r, "linear", (normalized,weight),
                   (b,s,fp), dict(mac=rows*h*fp))
        activated = local(f"{prefix}/gelu", r, "gelu_erf", (up,), (b,s,fp),
            dict(scalar_mul=3*rows*fp, scalar_add=rows*fp, scalar_erf=rows*fp))
        weight = parameter(f"{prefix}/wdown", (fp,h), r)
        ffn_partials.append(local(f"{prefix}/ffn_down", r, "linear", (activated,weight),
                                 (b,s,h), dict(mac=rows*fp*h)))
    ffn_results = sum_allreduce("ffn_sum", ffn_partials)
    for r in range(p):
        local(f"r{r}/output", r, "add", (residuals[r],ffn_results[r]),
              (b,s,h), dict(scalar_add=elements), retain=True)
    workload = Workload(tuple(data), tuple(operations))
    validate(workload)
    return Block(workload, tensors, operators, operation_workers, data_workers,
                 tuple(collectives), dims)
