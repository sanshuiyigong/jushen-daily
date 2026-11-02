# 待读队列 · 2026-11-02

> 离线重算：共 101 条新内容
> 手机级（≥7.0）：14 条 · 电脑级（≥5.0）：23 条

挑一条，读两小时。手机端只推第一条。

---

## 🔥 值得花时间（7.0+）

### 1. `8.33` RoboArchitect: Automating the Design of Robotic Agents with Persistent Memory

- 控制 · arxiv_ro · 2.9 天前
- [arXiv](https://arxiv.org/abs/2610.42141) · [PDF](https://arxiv.org/pdf/2610.42141v1) · [代码](https://github.com/roboarchitect-ai/RoboArchitect) · [主页](https://roboarchitect-ai.github.io/)
- Recent work shows that a frozen robot policy performs far better inside an agent harness, where control code decides when to query the policy, consult vision tools, or command the arm directly. Yet today these harnesses are built by hand and redesigned for eac…
- 命中关键词：manipulation, grasp, policy

- [ ] 已读

### 2. `8.31` REA: A Routed Embodied Agent Runtime for Asynchronous Brain-Cerebellum Control

- 控制 · arxiv_ro · 2.9 天前
- [arXiv](https://arxiv.org/abs/2610.42053) · [PDF](https://arxiv.org/pdf/2610.42053v1) · [主页](https://mikeeeeeeeeeeeeee.github.io/REA/)
- Foundation models are becoming remarkably reliable at high-level reasoning, yet they remain too slow and costly to serve as fine-grained controllers. Conversely, fast policies like VLAs and whole-body controllers offer more efficient reflexes, but struggle to …
- 命中关键词：vla, embodied, policy

- [ ] 已读

### 3. `8.31` Nexus-VLA: Bridging Human and Robot Experiences via a Shared Hierarchical Semantic Latent Space

- 感知 · arxiv_ro · 2.9 天前
- [arXiv](https://arxiv.org/abs/2610.42021) · [PDF](https://arxiv.org/pdf/2610.42021v1)
- Large-scale egocentric human videos provide rich and scalable manipulation experience for robot policy learning, yet substantial embodiment gaps in visual appearance, kinematic structure, and action spaces hinder effective knowledge transfer. Existing methods …
- 命中关键词：vla, manipulation, policy

- [ ] 已读

### 4. `8.10` When the Past Shapes Action: Understanding Embodied Memory

- 感知 · arxiv_ro · 3.1 天前
- [arXiv](https://arxiv.org/abs/2610.41688) · [PDF](https://arxiv.org/pdf/2610.41688v1)
- Recent advances in generative foundation models have expanded the capabilities of embodied AI, enabling increasingly general navigation, manipulation, and long-horizon task execution. However, effective interaction with dynamic environments requires more than …
- 命中关键词：embodied, manipulation

- [ ] 已读

### 5. `7.75` VLA Policies Do Not Know When Not to Act: Unintended Task Execution and Start Suppression

- 感知 · arxiv_ro · 3.1 天前
- [arXiv](https://arxiv.org/abs/2610.41609) · [PDF](https://arxiv.org/pdf/2610.41609v1)
- A robot should act only on an instruction from a person or on an intent that the robot explicitly represents and generates. Unintended actions taken without such an instruction can cause risk or inconvenience to people and the environment. We examine how recen…
- 命中关键词：vla, policy

- [ ] 已读

### 6. `7.65` CaPtain: A Pipeline for Post-Training Code-as-Policy Robot Agents

- 感知 · hf_papers · 4.6 天前
- [arXiv](https://arxiv.org/abs/2610.40799) · [PDF](https://arxiv.org/pdf/2610.40799) · [代码](https://github.com/waltstephen/CaPtain) · [主页](https://waltstephen.github.io/captain/)
- CaPtain trains small open vision-language models via supervised fine-tuning and multi-turn reinforcement learning with a physical critic to perform robot manipulation through code, achieving strong results without frontier models or vision-language-action back…
- 命中关键词：manipulation, policy

- [ ] 已读

### 7. `7.58` Online Learning of Heterogeneous Locomotion Dynamics under Reinforcement Learning Policies for Precise Loco-Manipulation

- 控制 · arxiv_ro · 3.0 天前
- [arXiv](https://arxiv.org/abs/2610.41892) · [PDF](https://arxiv.org/pdf/2610.41892v1)
- How to reuse a pretrained locomotion policy for precise loco-manipulation is still an open problem. We propose an online method to learn the closed-loop dynamics under a frozen locomotion policy. The learned model predicts floating-base motion and improves loc…
- 命中关键词：manipulation, policy

- [ ] 已读

### 8. `7.57` RTPolicy: Real-Time (32.9 Hz) Multi-View Visuomotor Policy for Robotic Manipulation on Edge Devices

- 感知 · arxiv_ro · 3.1 天前
- [arXiv](https://arxiv.org/abs/2610.41625) · [PDF](https://arxiv.org/pdf/2610.41625v1)
- Low inference latency is critical for closed-loop robotic manipulation, especially under asynchronous inference, where action chunks must be updated promptly to correct accumulated deviations. However, existing visuomotor policies rely on computationally expen…
- 命中关键词：manipulation, policy

- [ ] 已读

### 9. `7.57` Direct Action-Manifold Modeling for Efficient and Robust Bimanual Manipulation

- 控制 · arxiv_ro · 3.1 天前
- [arXiv](https://arxiv.org/abs/2610.41643) · [PDF](https://arxiv.org/pdf/2610.41643v1)
- Diffusion and flow matching visuomotor policies require iterative denoising or numerical integration for multimodal action generation, introducing latency and execution mismatch. We instead consider a different formulation: conditioned on vision and propriocep…
- 命中关键词：manipulation, policy

- [ ] 已读

### 10. `7.42` Design and Validation of a Robotic Knee Exoskeleton with Musculoskeletal Simulation-Derived Biological Torque Control

- 控制 · arxiv_ro · 2.9 天前
- [arXiv](https://arxiv.org/abs/2610.41981) · [PDF](https://arxiv.org/pdf/2610.41981v1)
- Data-driven controllers have enabled lower-limb robotic exoskeletons to adapt assistance to the user across many tasks. A leading example is biological torque control, which estimates the user's own joint moment from onboard sensors and assists in proportion t…
- 命中关键词：imitation, policy

- [ ] 已读

### 11. `7.42` Sensorium: An Open-Source Multimodal Data Collection and Curation Library for Embodied Surgical AI

- 通用 · arxiv_ro · 3.0 天前
- [arXiv](https://arxiv.org/abs/2610.41946) · [PDF](https://arxiv.org/pdf/2610.41946v1)
- Embodied surgical AI requires reliable multimodal data, yet surgical data collection remains costly, difficult to repeat, and strongly dependent on the hardware setup. We present Sensorium, an open-source Python library for recording, processing, annotating, a…
- 命中关键词：embodied, ros

- [ ] 已读

### 12. `7.40` FOCUS: First-Order Control Using Optimal Transport Supervision for Imitation from Observations

- 控制 · arxiv_ro · 3.2 天前
- [arXiv](https://arxiv.org/abs/2610.41540) · [PDF](https://arxiv.org/pdf/2610.41540v1)
- Imitation learning from observations must recover behavior from state-only demonstrations without known temporal correspondence. Differentiable simulators provide pathwise policy gradients, but differentiating through long, contact-rich trajectories can make o…
- 命中关键词：imitation, policy

- [ ] 已读

### 13. `7.22` $\nabla$Mimic: Ultra-Efficient Humanoid Control with Differentiable Simulation

- 控制 · arxiv_ro · 3.1 天前
- [arXiv](https://arxiv.org/abs/2610.41654) · [PDF](https://arxiv.org/pdf/2610.41654v1)
- Robot policy learning is dominated by zeroth-order methods such as PPO, which treat the simulator as a black box and pay for it with enormous sample counts. First-order policy learning differentiates through the dynamics, but on contact-rich whole-body control…
- 命中关键词：policy, mujoco

- [ ] 已读

### 14. `7.05` Visual-Inertial RGB-D SLAM with Encoders for a Differential Wheeled Robot

- 感知 · arxiv_ro · 3.0 天前
- [arXiv](https://arxiv.org/abs/2610.41768) · [PDF](https://arxiv.org/pdf/2610.41768v1)
- Recent years have seen multiple impressive results in visual-inertial odometry (VIO) techniques, by which accurate state estimation can be achieved via the extended Kalman filter (EKF) or nonlinear optimization. However, these approaches are rarely open source…
- 命中关键词：slam, vio

- [ ] 已读

---

## 📋 备选（5.0–7.0）

### 1. `6.38` Suspended-Fabric Robotic Manipulation Surfaces: Modelling, Design Space, and Multimodular Extensio

- 控制 · arxiv_ro · 2.9 天前
- [arXiv](https://arxiv.org/abs/2610.41982) · [PDF](https://arxiv.org/pdf/2610.41982v1)
- Robotic Manipulation Surfaces (RMS) reposition objects by deforming the surface on which they rest. A recent class of RMS suspends a continuous fabric sheet from a sparse grid of vertical linear actuators lowering the actuator density of such surfaces but how …
- 命中关键词：manipulation

- [ ] 已读

### 2. `6.35` Flexibility-Aware Robotic Manipulation: Deformation Estimation, Kinematics, and Control via Distributed Inertial Measurement

- 控制 · arxiv_ro · 3.1 天前
- [arXiv](https://arxiv.org/abs/2610.41702) · [PDF](https://arxiv.org/pdf/2610.41702v1)
- Flexible robot links challenge the rigid-body assumption, making joint measurements alone insufficient for accurate manipulation. This paper introduces a flexibility-aware manipulation framework that connects structural dynamics directly to sensing, kinematics…
- 命中关键词：manipulation

- [ ] 已读

### 3. `6.05` ROOF: Learning Humanoid Fall Recovery under Overhead Constraints

- 通用 · arxiv_ro · 2.9 天前
- [arXiv](https://arxiv.org/abs/2610.42097) · [PDF](https://arxiv.org/pdf/2610.42097v1)
- A fallen humanoid beneath an overhead obstacle faces a coupled recovery problem. It must create clearance while organizing support for a stable rise, since attempting to stand before making room can further increase obstruction. We introduce a reinforcement le…
- 命中关键词：policy

- [ ] 已读

### 4. `6.00` When the Simulator Fails, Not the Policy: Auditing Contact Artifacts in Simulated Robot Benchmarks

- 感知 · arxiv_ro · 3.0 天前
- [arXiv](https://arxiv.org/abs/2610.41857) · [PDF](https://arxiv.org/pdf/2610.41857v1)
- Simulation benchmarks score robot policies by success rate, and every failed episode counts against the policy. Many of these failures are the simulator's fault, not the policy's; we find the cause and fix it. Testing a vision language action model and a world…
- 命中关键词：policy

- [ ] 已读

### 5. `6.00` ResMerge: Residual Policy Learning and Merging for Continual Adaptation of Pre-trained Robot Policies

- 通用 · arxiv_ro · 3.1 天前
- [arXiv](https://arxiv.org/abs/2610.41663) · [PDF](https://arxiv.org/pdf/2610.41663v1)
- Continual adaptation to new tasks is essential for robots deployed in the real world, but adapting pre-trained policies remains challenging due to parameter growth and the need for continual demonstration collection. Parameter-Efficient Continual Fine-Tuning (…
- 命中关键词：policy

- [ ] 已读

### 6. `6.00` DrawSplat: Atlanta World-Guided Implicit Gaussian SLAM for Indoor Reconstruction

- 感知 · arxiv_ro · 3.2 天前
- [arXiv](https://arxiv.org/abs/2610.41602) · [PDF](https://arxiv.org/pdf/2610.41602v1)
- RGB-D SLAM requires accurate online tracking, high-quality rendering, and geometrically consistent reconstruction. Existing Gaussian SLAM methods mainly optimize Gaussian primitives with photometric, depth, or local frame-to-model constraints, which are often …
- 命中关键词：slam

- [ ] 已读

### 7. `6.00` AC-SMPC: Differentiable Actor--Critic MPC with State Constraints for Safe and Fast Robot Navigation

- 控制 · arxiv_ro · 3.2 天前
- [arXiv](https://arxiv.org/abs/2610.41477) · [PDF](https://arxiv.org/pdf/2610.41477v1)
- Achieving safe navigation in confined dynamic environments remains a challenging problem, as robots must balance navigation efficiency with safety. Existing actor--critic MPC architectures typically employ differentiable MPC layers, but this way cannot readily…
- 命中关键词：policy

- [ ] 已读

### 8. `5.70` tuotuoLyu/ForesightSafety-VLA

- 感知 · github · 4.5 天前
- [原文](https://github.com/tuotuoLyu/ForesightSafety-VLA)
- Official code for ForesightSafety-VLA (IROS 2026): a unified diagnostic safety benchmark for vision-language-action models on RoboTwin
- 命中关键词：vla
- ⭐ 87

- [ ] 已读

### 9. `5.13` rzc156/vla-diag

- 通用 · github · 18.3 天前
- [原文](https://github.com/rzc156/vla-diag)
- Check whether a VLA benchmark number is measuring what you think it measures — checkpoint integrity, failure taxonomy, headroom & power analysis (zero-dependency, framework-agnostic).
- 命中关键词：vla
- ⭐ 10

- [ ] 已读

---

## 🗑 已过滤（<5.0，共 78 条）

- `5.00` Hierarchical World Models with Implicit Dynamics
- `4.86` woolimi/robotics-roadmap
- `4.78` Movens-Zero: Scaling Humanoid Motion Foundation Models with Large-Scale Human Vi
- `4.78` META-Robot: Self-Cognition and Capability Scaling in Agentic Robots
- `4.15` gaoxiang12/ga-wm
- `4.13` Garfield-kh/FastVLA
- `3.93` Wizard: Manipulate Any World in Real Time via Agentic Control
- `3.90` HiFOR: Hierarchical Foresight with Action-Guided World Grounding for Vision-Lang
- `3.81` SketchMate: Agentic Geometric Reasoning for Zero-Shot Precision Insertion
- `3.80` WorldBridge: Bridging Video and Action for Task Generalization in World Action M
- `3.66` Broken on Arrival: Non-Functional Quantized LLM Artifacts in Public Model Regist
- `3.61` Language-Conditioned Behavioral Cloning for Autonomous Endoscope Guidance
- `3.60` Integrating Low-Thrust Transfer Dynamics into POMDP Planning for On-Orbit Servic
- `3.49` OpenVIO: A Versatile Open-Source Visual-Inertial Odometry System
- `3.45` On the Origin and Evolution of Training-Inference Mismatch in LLM Reinforcement 
- `3.43` Animan-AI/DuckBuddy
- `3.39` Higher-Order Kinematic Derivatives for Aspect-Preserving Real-Time Numerical Inv
- `3.36` Weaken to Strengthen: Weakening-Induced On-Policy Self-Distillation for Large Re
- `3.32` SemEllipsoid: Semantic-aware Shape Abstraction with Ellipsoid
- `3.27` xuyicheng-zju/TARSphere
- `3.16` Does Scaling Toward AGI Depend on What System-1 Lets System-2 Execute?
- `3.15` tuotuoLyu/FPO
- `3.11` HexaFuture/EmbodiedLab
- `3.10` Think in 360°: Benchmarking and Bootstrapping Panoramic Video Reasoning
- `3.09` FoAViS: Analyzing Learned Fixation Strategies in a Foveated Active Vision System
- …另有 53 条
