
.. include:: /_includes/rllib/we_are_hiring.rst

.. include:: /_includes/rllib/new_api_stack.rst

.. _rlmodule-reference-docs:

RLModule API
============


RL Module specifications and configurations
-------------------------------------------

Single Agent
++++++++++++

.. currentmodule:: ray.rllib.core.rl_module.rl_module

.. autosummary::
    :nosignatures:
    :toctree: doc/

    RLModuleSpec
    RLModuleSpec.build
    RLModuleSpec.get_rl_module_config

RLModule Configuration
+++++++++++++++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/

    RLModuleConfig
    RLModuleConfig.to_dict
    RLModuleConfig.from_dict
    RLModuleConfig.get_catalog

Multi RLModule (multi-agent)
++++++++++++++++++++++++++++

.. currentmodule:: ray.rllib.core.rl_module.multi_rl_module

.. autosummary::
    :nosignatures:
    :toctree: doc/

    MultiRLModuleSpec
    MultiRLModuleSpec.build
    MultiRLModuleSpec.get_multi_rl_module_config



RL Module API
-------------

.. currentmodule:: ray.rllib.core.rl_module.rl_module


Constructor
+++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/

    RLModule
    RLModule.as_multi_rl_module


Forward methods
+++++++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/


    ~RLModule.forward_train
    ~RLModule.forward_exploration
    ~RLModule.forward_inference
    ~RLModule._forward_train
    ~RLModule._forward_exploration
    ~RLModule._forward_inference

IO specifications
+++++++++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/

    ~RLModule.input_specs_inference
    ~RLModule.input_specs_exploration
    ~RLModule.input_specs_train
    ~RLModule.output_specs_inference
    ~RLModule.output_specs_exploration
    ~RLModule.output_specs_train



Saving and Loading
++++++++++++++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/

    ~RLModule.get_state
    ~RLModule.set_state
    ~RLModule.save_to_path
    ~RLModule.restore_from_path
    ~RLModule.from_checkpoint


Multi Agent RL Module API
-------------------------

.. currentmodule:: ray.rllib.core.rl_module.multi_rl_module

Constructor
+++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/

    MultiRLModule
    MultiRLModule.setup
    MultiRLModule.as_multi_rl_module

Modifying the underlying RL modules
++++++++++++++++++++++++++++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/

    ~MultiRLModule.add_module
    ~MultiRLModule.remove_module

Saving and Loading
++++++++++++++++++++++

.. autosummary::
    :nosignatures:
    :toctree: doc/

    ~MultiRLModule.save_to_path
    ~MultiRLModule.restore_from_path
