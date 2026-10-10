// Observation-only functions; used only in isolated G1 builds.
#ifndef WAFER_CAUSAL_SERVICE_HPP
#define WAFER_CAUSAL_SERVICE_HPP
void WaferLocalServiceFinish();
void WaferCausalEndpointCredit(int endpoint, int cycle, int amount);
#endif
