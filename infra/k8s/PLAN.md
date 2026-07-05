# Kubernetes migration plan (Phase 3+)
Not built this round — docker-compose is the dev/starter target. Path when scaling:

1. Helm chart per service; shared values for NATS/Redis/PG endpoints (managed or operators).
2. GPU node pool: label `gpu=true`; stt/tts pods get nodeSelector + `nvidia.com/gpu: 1` requests.
   Separate pools per workload (STT pool, TTS pool) so one can't starve the other —
   same principle as the per-GPU layout in dev.
3. Autoscaling: HPA on custom metric `active_sessions_per_pod` (exported by gateway),
   not CPU — GPU inference saturates before CPU does.
4. Asterisk: StatefulSet + hostNetwork (RTP port ranges), or better: run at edge VMs
   outside k8s and keep only the ARI controller in-cluster.
5. Ingress: nginx for REST; WS sessions need sticky routing (session affinity by session_id).
6. Storage: swap MinIO for S3/GCS via env; RDS/CloudSQL for PG.
7. Capacity ballpark: 1× L4 ≈ 15-30 concurrent STT streams OR 8-20 TTS streams (model-dependent);
   plan 1 GPU per ~10 concurrent full-duplex calls as a safe start, then measure.
