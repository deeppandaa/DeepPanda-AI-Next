import json

import cupy as cp

SRC = r'''
extern "C" __global__ void mma_f32acc(float* out, int iters) {
    unsigned a0 = threadIdx.x, a1 = a0 ^ 1u, a2 = a0 ^ 2u, a3 = a0 ^ 3u;
    unsigned b0 = a0 ^ 5u, b1 = a0 ^ 6u;
    float c[8][4];
    #pragma unroll
    for (int k = 0; k < 8; ++k) { c[k][0] = c[k][1] = c[k][2] = c[k][3] = 0.f; }
    for (int i = 0; i < iters; ++i) {
        #pragma unroll
        for (int k = 0; k < 8; ++k) {
            asm volatile("mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 "
                "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};"
                : "+f"(c[k][0]), "+f"(c[k][1]), "+f"(c[k][2]), "+f"(c[k][3])
                : "r"(a0), "r"(a1), "r"(a2), "r"(a3), "r"(b0), "r"(b1));
        }
    }
    float s = 0.f;
    #pragma unroll
    for (int k = 0; k < 8; ++k) s += c[k][0] + c[k][1] + c[k][2] + c[k][3];
    out[blockIdx.x * blockDim.x + threadIdx.x] = s;
}
extern "C" __global__ void mma_f16acc(float* out, int iters) {
    unsigned a0 = threadIdx.x, a1 = a0 ^ 1u, a2 = a0 ^ 2u, a3 = a0 ^ 3u;
    unsigned b0 = a0 ^ 5u, b1 = a0 ^ 6u;
    unsigned c[8][2];
    #pragma unroll
    for (int k = 0; k < 8; ++k) { c[k][0] = c[k][1] = 0u; }
    for (int i = 0; i < iters; ++i) {
        #pragma unroll
        for (int k = 0; k < 8; ++k) {
            asm volatile("mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16 "
                "{%0,%1}, {%2,%3,%4,%5}, {%6,%7}, {%0,%1};"
                : "+r"(c[k][0]), "+r"(c[k][1])
                : "r"(a0), "r"(a1), "r"(a2), "r"(a3), "r"(b0), "r"(b1));
        }
    }
    unsigned s = 0u;
    #pragma unroll
    for (int k = 0; k < 8; ++k) s ^= c[k][0] ^ c[k][1];
    out[blockIdx.x * blockDim.x + threadIdx.x] = (float)s;
}
'''


def main() -> None:
    mod = cp.RawModule(code=SRC, options=("-arch=sm_89",))
    props = cp.cuda.runtime.getDeviceProperties(0)
    sms = props["multiProcessorCount"]
    threads, blocks, iters = 256, sms * 8, 4096
    out = cp.zeros(blocks * threads, dtype=cp.float32)
    warps = blocks * threads // 32
    flop = warps * iters * 8 * (2 * 16 * 8 * 16)

    def run(name: str, reps: int = 7) -> float:
        kernel = mod.get_function(name)
        for _ in range(2):
            kernel((blocks,), (threads,), (out, cp.int32(iters)))
        cp.cuda.Device().synchronize()
        results = []
        for _ in range(reps):
            start, end = cp.cuda.Event(), cp.cuda.Event()
            start.record()
            kernel((blocks,), (threads,), (out, cp.int32(iters)))
            end.record()
            end.synchronize()
            results.append(flop / (cp.cuda.get_elapsed_time(start, end) / 1e3) / 1e12)
        results.sort()
        return results[len(results) // 2]

    rounds = [{"f16acc": run("mma_f16acc"), "f32acc": run("mma_f32acc")} for _ in range(3)]
    f16 = sorted(r["f16acc"] for r in rounds)[1]
    f32 = sorted(r["f32acc"] for r in rounds)[1]
    print(json.dumps({
        "gpu": props["name"].decode(),
        "sms": sms,
        "rounds_tflops": [{k: round(v, 2) for k, v in r.items()} for r in rounds],
        "median_f16acc_tflops": round(f16, 2),
        "median_f32acc_tflops": round(f32, 2),
        "f32acc_over_f16acc": round(f32 / f16, 3),
        "scope": "Synthetic MMA instruction throughput, not an unlock-off/on or Ollama comparison.",
    }, indent=2))


if __name__ == "__main__":
    main()
