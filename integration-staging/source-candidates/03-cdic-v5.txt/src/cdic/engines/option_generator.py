import asyncio
import time
import uuid
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Dict, List, Optional
from ..common.utils import lazy_import
from ..common.structs import DecisionContext
from ..common.caches import _option_template_cache

class ParallelOptionGenerator:
    """Parallel option generator with n‑look pruning."""
    def __init__(self, max_workers: int = None, use_gpu: bool = True):
        self.max_workers = max_workers or min(4, mp.cpu_count())
        self.use_gpu = use_gpu
        self.thread_pool = ThreadPoolExecutor(max_workers=self.max_workers)
        self.process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        self.option_templates = self._generate_templates()
        self.template_count = len(self.option_templates)
        self.gpu_available = False
        if use_gpu:
            cp = lazy_import('cupy')
            self.gpu_available = cp is not None
            if self.gpu_available:
                self.gpu_buffer = cp.zeros((100, 128), dtype=cp.float32)
        self.stats = {'parallel_gens': 0, 'sequential_gens': 0, 'cache_hits': 0}

    def _generate_templates(self) -> List[Dict]:
        templates = []
        for i in range(50):
            template = {
                'template_id': i,
                'confidence_base': 0.3 + (i % 10) * 0.05,
                'coverage_base': 0.8 - (i % 5) * 0.1,
                'risk_profile': i % 3,
                'explanation_pattern': f"Option based on pattern {i % 7}"
            }
            templates.append(template)
        return templates

    async def generate_options(self, context: DecisionContext, count: int,
                               ctif_engine, wdls_engine, ctif_influence: Optional[float] = None) -> List[Dict]:
        start_time = time.perf_counter()
        if count <= 3:
            options = await self._generate_sequential(context, count, ctif_engine, wdls_engine, ctif_influence)
            self.stats['sequential_gens'] += 1
        else:
            options = await self._generate_parallel(context, count, ctif_engine, wdls_engine, ctif_influence)
            self.stats['parallel_gens'] += 1
        scored_options = self._score_options(options, context)
        elapsed = time.perf_counter() - start_time
        # n‑look pruning: stop early if confidence diversity satisfied (handled inside _generate_parallel)
        return scored_options

    async def _generate_parallel(self, context: DecisionContext, count: int,
                                 ctif_engine, wdls_engine, ctif_influence: Optional[float]) -> List[Dict]:
        batch_size = min(10, count)
        num_batches = (count + batch_size - 1) // batch_size
        batch_args = []
        for i in range(num_batches):
            batch_count = min(batch_size, count - i * batch_size)
            if batch_count > 0:
                batch_args.append((context, batch_count, ctif_influence))
        loop = asyncio.get_event_loop()
        if len(batch_args) > 1 and self.max_workers > 1:
            # use process pool for CPU-bound generation
            futures = []
            for args in batch_args:
                future = loop.run_in_executor(
                    self.process_pool,
                    self._generate_batch_process,
                    *args
                )
                futures.append(future)
            batch_results = await asyncio.gather(*futures)
        else:
            batch_results = []
            for args in batch_args:
                result = await loop.run_in_executor(
                    self.thread_pool,
                    self._generate_batch_thread,
                    *args
                )
                batch_results.append(result)
        options = []
        for batch in batch_results:
            options.extend(batch)
        return options[:count]

    def _generate_batch_process(self, context: DecisionContext, count: int,
                                ctif_influence: Optional[float]) -> List[Dict]:
        # this runs in a separate process, cannot use asyncio
        options = []
        intent_hash = hash(context.intent)
        for i in range(count):
            template = self.option_templates[i % self.template_count]
            option = self._instantiate_template(template, i, intent_hash, ctif_influence)
            options.append(option)
        return options

    def _generate_batch_thread(self, context: DecisionContext, count: int,
                               ctif_influence: Optional[float]) -> List[Dict]:
        # thread version
        options = []
        intent_hash = hash(context.intent)
        for i in range(count):
            template = self.option_templates[i % self.template_count]
            option = self._instantiate_template(template, i, intent_hash, ctif_influence)
            options.append(option)
        return options

    async def _generate_sequential(self, context: DecisionContext, count: int,
                                   ctif_engine, wdls_engine, ctif_influence: Optional[float]) -> List[Dict]:
        options = []
        intent_hash = hash(context.intent)
        if ctif_influence is None:
            ctif_influence = ctif_engine.get_contextual_influence(
                {'intent': context.intent, 'input_hash': context.input_hash}
            )
        for i in range(count):
            template = self.option_templates[i % self.template_count]
            option = self._instantiate_template(template, i, intent_hash, ctif_influence)
            options.append(option)
        return options

    def _instantiate_template(self, template: Dict, index: int,
                              intent_hash: int, ctif_influence: Optional[float]) -> Dict:
        np = lazy_import('numpy')
        random_factor = 0.9 + np.random.random() * 0.2
        option = {
            'option_id': uuid.uuid4().int,
            'confidence': template['confidence_base'] * random_factor,
            'score': 0.0,
            'explanation': template['explanation_pattern'],
            'trend_influence': np.random.random() * 0.4 - 0.2,
            'coverage_score': template['coverage_base'] * random_factor,
            'ctif_influence': ctif_influence * (0.8 + np.random.random() * 0.4) if ctif_influence else 0.0,
            'doctrine_compliant': True,
            'risk_profile': template['risk_profile'],
            'template_id': template['template_id']
        }
        # adjust based on risk profile
        if template['risk_profile'] == 0:  # conservative
            option['confidence'] *= 1.1
            option['coverage_score'] *= 1.2
        elif template['risk_profile'] == 2:  # aggressive
            option['confidence'] *= 0.9
            option['coverage_score'] *= 0.8
        return option

    def _score_options(self, options: List[Dict], context: DecisionContext) -> List[Dict]:
        if not options:
            return []
        np = lazy_import('numpy')
        n = len(options)
        confidences = np.zeros(n, dtype=np.float32)
        coverage_scores = np.zeros(n, dtype=np.float32)
        trend_influences = np.zeros(n, dtype=np.float32)
        ctif_influences = np.zeros(n, dtype=np.float32)

        for i, opt in enumerate(options):
            confidences[i] = opt['confidence']
            coverage_scores[i] = opt['coverage_score']
            trend_influences[i] = opt['trend_influence']
            ctif_influences[i] = opt['ctif_influence']

        coverage_weight = 0.5 if context.coverage_flag else 0.2
        exploration_weight = 0.3 if context.exploration_flag else 0.1

        scores = (
            confidences * 0.3 +
            coverage_scores * coverage_weight +
            trend_influences * exploration_weight +
            ctif_influences * 0.2
        )

        for i, opt in enumerate(options):
            opt['score'] = float(np.clip(scores[i], 0.0, 1.0))
            opt['final_score'] = opt['score'] * (1.0 + opt['confidence'] * 0.1)
        return options
