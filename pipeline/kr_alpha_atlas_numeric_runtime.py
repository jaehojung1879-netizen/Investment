"""CPU kernel identity for the single Phase C study; standard library only.

Imported before NumPy. Version/package/thread pins alone do not pin SIMD math.
This restricts dispatch, not feature arithmetic, precision or the digest gate.
"""
from __future__ import annotations

import os
import sys

ENVIRONMENT = {
    'PYTHONHASHSEED': '1',
    'OPENBLAS_CORETYPE': 'Haswell',
    'NPY_DISABLE_CPU_FEATURES': 'AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,AVX512_CNL,AVX512_ICL',
}


def bootstrap():
    """Bind before numerical imports; re-exec only to establish Python hash seed."""
    if 'numpy' in sys.modules:
        raise RuntimeError('NUMERICAL_KERNEL_MUST_BE_BOUND_BEFORE_NUMPY_IMPORT')
    restart = os.environ.get('PYTHONHASHSEED') != ENVIRONMENT['PYTHONHASHSEED']
    for key, value in ENVIRONMENT.items():
        current = os.environ.get(key)
        if current is not None and current != value:
            raise RuntimeError('CONFLICTING_REGISTERED_NUMERICAL_ENVIRONMENT: '+key)
        os.environ[key] = value
    if restart:
        os.execve(sys.executable, [sys.executable, *sys.argv], dict(os.environ))


def verify(spec):
    # Importing here deliberately follows bootstrap or an explicitly pinned process.
    from numpy._core import _multiarray_umath
    from threadpoolctl import threadpool_info
    from pipeline.kr_alpha_atlas_phase_c import preflight
    runtime = preflight.verify_runtime(spec)
    cpu = _multiarray_umath.__cpu_features__
    if not cpu.get('AVX2') or not cpu.get('FMA3') or any(cpu.get(k) for k in ENVIRONMENT['NPY_DISABLE_CPU_FEATURES'].split(',')):
        raise ValueError('REGISTERED_AVX2_WITHOUT_AVX512_DISPATCH_REQUIRED')
    pools = [p for p in threadpool_info() if p['user_api'] == 'blas']
    if not pools or any(p['internal_api'] != 'openblas' or p['architecture'] != 'Haswell' or p['num_threads'] != 1 for p in pools):
        raise ValueError('REGISTERED_SINGLE_THREAD_HASWELL_BLAS_REQUIRED')
    runtime['numericalKernel'] = {'environment': ENVIRONMENT, 'blasVersions': sorted(p['version'] for p in pools)}
    return runtime
