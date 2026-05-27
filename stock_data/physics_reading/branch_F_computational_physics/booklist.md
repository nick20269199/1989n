# Branch F: 计算物理与机器学习 — 书单 (50本)

## 概况
| 维度 | 数值 |
|------|------|
| 子域 | 计算物理与机器学习 (Computational Physics & ML) |
| 本数 | 50本 |
| Agent相关性 | ★★★ AI/ML物理基础，Monte Carlo方法=信念采样/更新 |
| 跨域 | 哲学(计算主义/自由意志)、经济(随机过程/数值优化) |

## Part 1: 计算物理经典方法 (15本)

| # | 作者 | 著作 | 核心贡献 | Agent映射 |
|---|------|------|---------|----------|
| 1 | Press, Teukolsky, Vetterling, Flannery | 《Numerical Recipes》 (1986-2007, 3rd ed) | 数值方法圣经，涵盖FFT/ODE/随机数/优化 | Agent的"数值工具包"—每种方法对应一种推理模式 |
| 2 | Landau & Binder | 《Monte Carlo Simulations in Statistical Physics》 (2000, 3rd ed) | MC方法在统计物理的权威指南 | Agent的不确定性采样=信念空间的Monte Carlo |
| 3 | Frenkel & Smit | 《Understanding Molecular Simulation》 (2001, 2nd ed) | MD模拟的算法与实践 | Agent的"时间演化"=系统的分子动力学 |
| 4 | Thijssen | 《Computational Physics》 (2007, 2nd ed) | 最全面的计算物理教材 | Agent作为"数值计算器"的计算成本约束 |
| 5 | Newman | 《Computational Physics》 (2012) | 现代Python计算物理入门 | 从算法到代码的完整链路=Agent的认知流水线 |
| 6 | Metropolis, Rosenbluth, Rosenbluth, Teller & Teller | 《Equation of State by Fast Computing Machines》 (1953, JCP) | 原始Metropolis算法论文 | 重要性采样=Agent在处理高维不确定性时最有效的策略 |
| 7 | Hastings | 《Monte Carlo Sampling Using Markov Chains》 (1970, Biometrika) | MCMC的通用框架 | MCMC=Agent的信念更新引擎 |
| 8 | Binder & Heermann | 《Monte Carlo Simulation in Statistical Physics》 (2010) | MC实现细节 | Agent的有限样本误差控制 |
| 9 | Hamming | 《Numerical Methods for Scientists and Engineers》 (1962) | 经典数值分析 | "计算不是魔法是工程"—Agent的数值可靠性 |
| 10 | Koonin | 《Computational Physics》 (1986) | FORTRAN世代计算物理 | 计算物理的底层逻辑=离散化/迭代/收敛 |
| 11 | Gould, Tobochnik & Christian | 《An Introduction to Computer Simulation Methods》 (2006, 3rd ed) | 通过仿真学物理 | Agent通过仿真(mental simulation)预演决策结果 |
| 12 | Pang | 《An Introduction to Computational Physics》 (2006, 2nd ed) | 覆盖PDE/FFT/量子计算 | Agent的连续/离散信号处理 |
| 13 | Rapaport | 《The Art of Molecular Dynamics Simulation》 (2004, 2nd ed) | MD的艺术级实现 | Agent系统的"轨迹预测"=MD的时间积分 |
| 14 | Garcia | 《Numerical Methods for Physics》 (1999, 2nd ed) | 物理数值方法入门 | 近似误差理论→Agent的近似推理边界 |
| 15 | Vesely | 《Computational Physics: An Introduction》 (2001, 2nd ed) | 计算的物理视角 | 计算=物理过程(耗能/耗时/lower bound) |

## Part 2: 统计物理与学习理论 (10本)

| # | 作者 | 著作 | 核心贡献 | Agent映射 |
|---|------|------|---------|----------|
| 16 | Mézard, Parisi, Virasoro | 《Spin Glass Theory and Beyond》 (1987) | 自旋玻璃的replica方法 | 复制法→Agent的"多重假设"并行竞争框架 |
| 17 | Engel & Van den Broeck | 《Statistical Mechanics of Learning》 (2001) | 统计物理→学习理论桥接 | 泛化误差=统计物理中的自由能最小化 |
| 18 | Nishimori | 《Statistical Physics of Spin Glasses and Information Processing》 (2001) | 信息论→统计物理 | 退火/淬火=Agent的探索率调度 |
| 19 | Opper & Saad | 《Advanced Mean Field Methods》 (2001) | 平均场方法在ML中 | Agent群体的平均场近似=忽略个体细粒度互动 |
| 20 | Coolen | 《A Theory of Learning and Generalization》 (1998) | 学习的形式理论 | Agent的学习=从训练样本到泛化的相变 |
| 21 | Watkin | 《The Statistical Physics of Neural Networks》 (1993, RMP) | 神经网络统计物理综述 | 学习=权重空间的统计力学 |
| 22 | Seung, Sompolinsky & Tishby | 《Statistical Mechanics of Learning》 (1990s论文体系) | 学习动力学的统计力学 | 学习曲线=相变曲线 |
| 23 | Bahri et al. | 《Statistical Mechanics of Deep Learning》 (2020, ARPC) | 深度学习在统计物理框架下理解 | Agent的深层推理=多层级相变 |
| 24 | Mehta et al. | 《A High-Bias, Low-Variance Introduction to ML for Physicists》 (2019, Physics Reports) | 物理学家视角的ML导论 | 偏差-方差权衡=物理学的underfit-overfit |
| 25 | Montanari & Sen | 《A Gentle Introduction to the Statistics of High-Dimensional Data》 (近年讲义) | 高维统计 | 维数灾难→Agent的"太多变量"问题=统计物理 |

## Part 3: 神经网络与物理系统 (10本)

| # | 作者 | 著作 | 核心贡献 | Agent映射 |
|---|------|------|---------|----------|
| 26 | Hopfield | 《Neural Networks and Physical Systems》 (1982, PNAS) | Hopfield网络=物理系统记忆 | Agent的记忆=能量景观的局部极小 |
| 27 | Hertz, Krogh & Palmer | 《Introduction to the Theory of Neural Computation》 (1991) | 神经网络计算理论 | 神经计算=物理动力学的计算解读 |
| 28 | Amit | 《Modeling Brain Function》 (1989) | 吸引子神经网络 | Agent的"认知状态"=吸引子盆地 |
| 29 | Ackley, Hinton & Sejnowski | 《Boltzmann Machines》 (1985, Cognitive Science) | Boltzmann机=随机神经网络 | Agent的随机推理=热噪声驱动的状态跳转 |
| 30 | Hinton & Sejnowski | 《Learning in Boltzmann Machines》 (1986, PDP卷) | BM学习规则 | 对比散度=Agent的"现实vs幻想"差距学习 |
| 31 | Rumelhart & McClelland | 《Parallel Distributed Processing》 (1986, 2卷) | 分布式认知+反向传播 | Agent的认知=分布式表示(非符号) |
| 32 | MacKay | 《Information Theory, Inference, and Learning Algorithms》 (2003) | 信息论+贝叶斯+物理统一框架 | Agent的推断=编码=物理==三位一体 |
| 33 | Bishop | 《Neural Networks for Pattern Recognition》 (1995) | 神经网络+贝叶斯视角 | 正则化=物理中的偏置 |
| 34 | Haykin | 《Neural Networks: A Comprehensive Foundation》 (1998, 2nd ed) | 神经网络的全面基础 | Agent的非线性动力学=神经网络的动力学行为 |
| 35 | LeCun, Bengio & Hinton | 《Deep Learning》 (2015, Nature) | 深度学习革命综述 | Agent的层次抽象=学习的分层表示 |

## Part 4: 现代ML与物理融合 (10本)

| # | 作者 | 著作 | 核心贡献 | Agent映射 |
|---|------|------|---------|----------|
| 36 | Goodfellow, Bengio & Courville | 《Deep Learning》 (2016) | 深度学习综合教材 | Agent的内在表示学习=表征的层级抽象 |
| 37 | Murphy | 《Probabilistic Machine Learning》 (2022, 2卷) | 概率ML全面教材 | Agent的不确定性推理=概率图模型 |
| 38 | Raissi, Perdikaris & Karniadakis | 《Physics-Informed Neural Networks》 (2019, JCP) | PINNs=物理定律约束的ML | Agent的"物理知识"作为归纳偏置约束学习 |
| 39 | Brunton & Kutz | 《Data-Driven Science and Engineering》 (2019) | 数据驱动动力系统+SINDy | Agent从数据中"发现"控制方程=模式提取 |
| 40 | Carleo et al. | 《Machine Learning and the Physical Sciences》 (2019, RMP) | ML在物理学的全面综述 | 物理模拟遇到的"维数灾难"=Agent的维度诅咒 |
| 41 | Iten et al. | 《Discovering Physical Concepts with Neural Networks》 (2020, PRL) | NN自动发现物理概念 | Agent的"概念形成"=神经网络的表示发现 |
| 42 | Cranmer et al. | 《Symbolic Regression for Physics》 (2020, PNAS) | 符号回归发现物理定律 | Agent从数据发现可解释模式=符号回归 |
| 43 | Willard et al. | 《Integrating Physics and ML: A Survey》 (2020, arXiv) | 物理融入ML方法分类 | Agent的"先验=物理" vs "纯数据驱动" |
| 44 | Dunjko & Briegel | 《Machine Learning & Quantum Computing》 (2018, RMP) | 量子ML综述 | Agent的量子变体=量子增强算法 |
| 45 | Biamonte et al. | 《Quantum Machine Learning》 (2017, Nature) | 量子ML核心论文 | Agent的量子并行=指数加速 |

## Part 5: 计算思维与物理世界观 (5本)

| # | 作者 | 著作 | 核心贡献 | Agent映射 |
|---|------|------|---------|----------|
| 46 | Flake | 《The Computational Beauty of Nature》 (1998) | 计算/物理/生物/CA统一 | Agent的多学科统一计算视角=跨域类比引擎 |
| 47 | Pearl | 《Causality: Models, Reasoning and Inference》 (2009, 2nd ed) | 因果推断形式框架 | Agent从相关到因果=干预/反事实/do算子 |
| 48 | Pearl & Mackenzie | 《The Book of Why》 (2018) | 因果推理通俗 | Agent的"为什么"能力=因果梯子三级 |
| 49 | Russell | 《Human Compatible: AI and the Problem of Control》 (2019) | AI安全与对齐 | Agent的"价值学习"=不确定的人类偏好 |
| 50 | Pearl | 《Heuristics: Intelligent Search Strategies》 (1983) | 启发式搜索的形式理论基础 | Agent的搜索效率=启发式≈物理中的变分法 |
