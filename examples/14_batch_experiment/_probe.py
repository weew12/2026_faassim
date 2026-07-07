import pandas as pd
for case in ['default_skippy__low_load__seed_1', 'fixed_node__low_load__seed_1', 'default_skippy__medium_load__seed_1', 'fixed_node__medium_load__seed_1']:
    p = r'D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\{}\batch_invoke_probe.csv'.format(case)
    p_sched = r'D:\研\7毕设\2 大论文\修辅\07-06\faas-sim-master\examples\14_batch_experiment\outputs\runs\{}\schedule.csv'.format(case)
    probe = pd.read_csv(p)
    sched = pd.read_csv(p_sched)
    selected_nodes = sched[sched.value == 'finish']['node_name'].dropna().unique()
    print(f'{case}: probe node_names={sorted(probe.node_name.unique())}, scheduled_nodes={list(selected_nodes)}')