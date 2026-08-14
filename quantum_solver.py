import numpy as np
import time
import json
import os
from typing import Dict, List, Tuple, Any

# Optional Qiskit imports
HAS_QISKIT = False
HAS_AER = False
try:
    import qiskit
    from qiskit import QuantumCircuit
    from qiskit.primitives import Sampler
    # Qiskit Aer might be available
    try:
        from qiskit_aer import AerSimulator
        HAS_AER = True
    except ImportError:
        HAS_AER = False
    HAS_QISKIT = True
except ImportError:
    HAS_QISKIT = False

# Optional Azure Quantum imports
HAS_AZURE_QUANTUM = False
try:
    from azure.quantum import Workspace
    from azure.quantum.optimization import Problem, ProblemType, Term
    HAS_AZURE_QUANTUM = True
except ImportError:
    HAS_AZURE_QUANTUM = False


class ClassicalQubitSimulator:
    """
    A pure NumPy-based statevector simulator for QAOA to ensure 100% reliability
    even if Qiskit installation has issues on the host system.
    Supports up to ~14 qubits efficiently.
    """
    def __init__(self, num_qubits: int):
        self.num_qubits = num_qubits
        self.num_states = 1 << num_qubits
        self.state = np.zeros(self.num_states, dtype=complex)
        self.reset()

    def reset(self):
        # Start in state |0...0>
        self.state = np.zeros(self.num_states, dtype=complex)
        self.state[0] = 1.0

    def apply_hadamards(self):
        # Put all qubits in superposition |+>
        self.state = np.ones(self.num_states, dtype=complex) / np.sqrt(self.num_states)

    def apply_cost_hamiltonian(self, qubo_matrix: np.ndarray, gamma: float):
        """
        Applies exp(-i * gamma * H_C) to the statevector.
        Since H_C is diagonal in the computational basis, this is just a phase shift:
        state[s] = state[s] * exp(-i * gamma * E(s))
        """
        energies = np.zeros(self.num_states)
        for s in range(self.num_states):
            # Convert index to bit array (binary representation)
            bits = np.array([(s >> k) & 1 for k in range(self.num_qubits)])
            # Calculate QUBO energy: x^T * Q * x
            # E(x) = sum_i Q_ii x_i + sum_{i<j} Q_ij x_i x_j
            energy = 0.0
            for i in range(self.num_qubits):
                energy += qubo_matrix[i, i] * bits[i]
                for j in range(i + 1, self.num_qubits):
                    energy += qubo_matrix[i, j] * bits[i] * bits[j]
            energies[s] = energy
        
        # Apply phase factor
        phases = np.exp(-1j * gamma * energies)
        self.state = self.state * phases

    def apply_mixer_hamiltonian(self, beta: float):
        """
        Applies exp(-i * beta * H_M) where H_M = sum_i X_i.
        This is equivalent to applying X rotation R_x(2*beta) on each qubit.
        """
        # R_x(2*beta) = cos(beta)*I - i*sin(beta)*X
        c = np.cos(beta)
        s = -1j * np.sin(beta)
        rot = np.array([[c, s], [s, c]], dtype=complex)

        for qubit in range(self.num_qubits):
            # Reshape statevector to apply gate to the specified qubit
            # Qubit indexing: LSB corresponds to qubit 0
            shape = (2**(self.num_qubits - qubit - 1), 2, 2**qubit)
            self.state = self.state.reshape(shape)
            # Apply 2x2 rotation matrix to the middle dimension (size 2)
            self.state = np.einsum('ab,cbd->cad', rot, self.state)
            self.state = self.state.flatten()

    def get_probabilities(self) -> np.ndarray:
        return np.abs(self.state) ** 2


class QuantumOptimizationEngine:
    def __init__(self):
        pass

    @staticmethod
    def calculate_energy(bitstring: str, qubo_matrix: List[List[float]]) -> float:
        """Calculates QUBO energy for a given binary string."""
        x = [int(char) for char in bitstring]
        n = len(x)
        energy = 0.0
        for i in range(n):
            energy += qubo_matrix[i][i] * x[i]
            for j in range(i + 1, n):
                energy += qubo_matrix[i][j] * x[i] * x[j]
        return energy

    def solve_simulated_annealing(self, qubo_matrix: List[List[float]], 
                                  initial_temp: float = 10.0, 
                                  cooling_rate: float = 0.95, 
                                  num_steps: int = 200) -> Dict[str, Any]:
        """
        Solves the QUBO problem using classical Simulated Annealing.
        Returns the best configuration, its energy, and the convergence history.
        """
        Q = np.array(qubo_matrix)
        n = len(Q)
        
        # Start with a random binary state
        current_state = np.random.randint(0, 2, n)
        
        def get_energy(state):
            return state.dot(Q).dot(state) # For symmetric/upper-triangular Q
            
        current_energy = get_energy(current_state)
        
        best_state = current_state.copy()
        best_energy = current_energy
        
        temp = initial_temp
        history = []
        
        for step in range(num_steps):
            # Create neighbor by flipping one random bit
            flip_idx = np.random.randint(0, n)
            next_state = current_state.copy()
            next_state[flip_idx] = 1 - next_state[flip_idx]
            
            next_energy = get_energy(next_state)
            energy_diff = next_energy - current_energy
            
            # Metropolis Hastings criterion
            if energy_diff < 0 or np.random.rand() < np.exp(-energy_diff / temp):
                current_state = next_state
                current_energy = next_energy
                
                if current_energy < best_energy:
                    best_state = current_state.copy()
                    best_energy = current_energy
            
            history.append({
                "step": step,
                "temperature": temp,
                "energy": float(current_energy),
                "best_energy": float(best_energy)
            })
            
            # Cool down
            temp *= cooling_rate
            
        best_bitstring = "".join(map(str, best_state))
        
        return {
            "best_state": best_bitstring,
            "best_energy": float(best_energy),
            "history": history,
            "success": True,
            "method": "Simulated Annealing"
        }

    def solve_qaoa_classical_sim(self, qubo_matrix: List[List[float]], p: int = 1, iterations: int = 30) -> Dict[str, Any]:
        """
        Runs QAOA using our lightweight classical statevector simulator.
        Finds optimal parameters (gamma, beta) using classical minimization.
        """
        Q = np.array(qubo_matrix)
        n = len(Q)
        
        sim = ClassicalQubitSimulator(n)

        # Objective function for classical optimization (Scipy)
        # Returns the expectation value of energy for parameters gamma, beta
        def expectation_value(params):
            gamma, beta = params[0], params[1]
            sim.reset()
            sim.apply_hadamards()
            sim.apply_cost_hamiltonian(Q, gamma)
            sim.apply_mixer_hamiltonian(beta)
            probs = sim.get_probabilities()
            
            # Calculate expectation value of energy
            exp_val = 0.0
            for s in range(sim.num_states):
                bits = np.array([(s >> k) & 1 for k in range(n)])
                energy = bits.dot(Q).dot(bits)
                exp_val += probs[s] * energy
            return exp_val

        # Classical optimization loop (COBYLA)
        from scipy.optimize import minimize
        initial_params = [0.1, 0.1]
        
        history = []
        
        def callback(xk):
            val = expectation_value(xk)
            history.append({
                "iteration": len(history),
                "gamma": float(xk[0]),
                "beta": float(xk[1]),
                "expected_energy": float(val)
            })

        res = minimize(expectation_value, initial_params, method='COBYLA', 
                       options={'maxiter': iterations}, callback=callback)
        
        opt_gamma, opt_beta = res.x[0], res.x[1]
        
        # Get final state probabilities
        sim.reset()
        sim.apply_hadamards()
        sim.apply_cost_hamiltonian(Q, opt_gamma)
        sim.apply_mixer_hamiltonian(opt_beta)
        probs = sim.get_probabilities()
        
        # Sort states by probability
        state_probs = []
        for s in range(sim.num_states):
            bitstring = format(s, f'0{n}b')[::-1] # Reverse to match qubit convention (q0 on left/right depending on preference, here LSB is index 0)
            energy = self.calculate_energy(bitstring, qubo_matrix)
            state_probs.append({
                "bitstring": bitstring,
                "probability": float(probs[s]),
                "energy": energy
            })
            
        state_probs = sorted(state_probs, key=lambda x: x["probability"], reverse=True)
        
        # Best state is the one with highest probability or lowest energy found in top probs
        best_state = state_probs[0]["bitstring"]
        best_energy = state_probs[0]["energy"]
        
        # Generate circuit representation as string
        circuit_text = "Classical NumPy Simulator (Zero-latency)"
        if HAS_QISKIT:
            try:
                qc = QuantumCircuit(n)
                qc.h(range(n))
                # Cost layer
                for i in range(n):
                    if abs(Q[i, i]) > 1e-5:
                        qc.rz(2 * opt_gamma * Q[i, i], i)
                for i in range(n):
                    for j in range(i + 1, n):
                        if abs(Q[i, j]) > 1e-5:
                            qc.cx(i, j)
                            qc.rz(2 * opt_gamma * Q[i, j], j)
                            qc.cx(i, j)
                # Mixer layer
                qc.rx(2 * opt_beta, range(n))
                qc.measure_all()
                circuit_text = str(qc.draw(output='text'))
            except Exception as e:
                circuit_text = f"Qiskit circuit generation failed: {str(e)}"
        
        return {
            "best_state": best_state,
            "best_energy": float(best_energy),
            "opt_gamma": float(opt_gamma),
            "opt_beta": float(opt_beta),
            "expected_energy": float(res.fun),
            "state_probabilities": state_probs[:32], # Limit to top 32 for UI rendering
            "history": history,
            "circuit_text": circuit_text,
            "success": True,
            "method": "QAOA (Classical Simulation)"
        }

    def solve_qaoa_qiskit(self, qubo_matrix: List[List[float]], p: int = 1, iterations: int = 30) -> Dict[str, Any]:
        """
        Runs QAOA using standard Qiskit library.
        If Qiskit is not available, falls back to the classical simulator automatically.
        """
        if not HAS_QISKIT:
            return self.solve_qaoa_classical_sim(qubo_matrix, p, iterations)
            
        Q = np.array(qubo_matrix)
        n = len(Q)
        
        # Map QUBO to Ising Hamiltonian
        # H = sum_i h_i Z_i + sum_{i<j} J_{ij} Z_i Z_j
        # x_i = (1 - Z_i)/2
        # Linear: Q_ii x_i = Q_ii/2 (I - Z_i)
        # Quadratic: Q_ij x_i x_j = Q_ij/4 (I - Z_i - Z_j + Z_i Z_j)
        h = np.zeros(n)
        J = np.zeros((n, n))
        
        for i in range(n):
            h[i] -= Q[i, i] / 2.0
            for j in range(i + 1, n):
                h[i] -= Q[i, j] / 4.0
                h[j] -= Q[i, j] / 4.0
                J[i, j] += Q[i, j] / 4.0

        # Implement expectation calculation using Qiskit
        def get_qaoa_circuit(gamma, beta):
            qc = QuantumCircuit(n)
            # Hadamards
            qc.h(range(n))
            
            # P layers of Cost & Mixer
            for step in range(p):
                # Cost layer: exp(-i * gamma * H_C)
                # Z gates for linear terms
                for i in range(n):
                    if abs(h[i]) > 1e-6:
                        qc.rz(2 * gamma * h[i], i)
                # ZZ terms for quadratic terms
                for i in range(n):
                    for j in range(i + 1, n):
                        if abs(J[i, j]) > 1e-6:
                            qc.cx(i, j)
                            qc.rz(2 * gamma * J[i, j], j)
                            qc.cx(i, j)
                            
                # Mixer layer: exp(-i * beta * H_M)
                qc.rx(2 * beta, range(n))
                
            qc.measure_all()
            return qc

        # Since we need to run optimization, let's use the local Aer simulator if available,
        # otherwise fallback to BasicProvider or Qiskit's built-in Statevector/Sampler.
        sampler = Sampler()
        
        def expectation_value(params):
            gamma, beta = params[0], params[1]
            qc = get_qaoa_circuit(gamma, beta)
            
            # Execute circuit
            job = sampler.run(qc, shots=1024)
            result = job.result()
            quasi_dists = result.quasi_dists[0]
            
            # Compute expected energy
            exp_val = 0.0
            for int_state, prob in quasi_dists.items():
                bitstring = format(int_state, f'0{n}b')[::-1] # Match qubit convention
                # Evaluate QUBO energy
                energy = self.calculate_energy(bitstring, qubo_matrix)
                exp_val += prob * energy
            return exp_val

        from scipy.optimize import minimize
        initial_params = [0.1, 0.1]
        history = []
        
        def callback(xk):
            val = expectation_value(xk)
            history.append({
                "iteration": len(history),
                "gamma": float(xk[0]),
                "beta": float(xk[1]),
                "expected_energy": float(val)
            })

        try:
            res = minimize(expectation_value, initial_params, method='COBYLA', 
                           options={'maxiter': iterations}, callback=callback)
            
            opt_gamma, opt_beta = res.x[0], res.x[1]
            
            # Get final distribution
            final_qc = get_qaoa_circuit(opt_gamma, opt_beta)
            job = sampler.run(final_qc, shots=2048)
            quasi_dists = job.result().quasi_dists[0]
            
            state_probs = []
            for int_state, prob in quasi_dists.items():
                bitstring = format(int_state, f'0{n}b')[::-1]
                energy = self.calculate_energy(bitstring, qubo_matrix)
                state_probs.append({
                    "bitstring": bitstring,
                    "probability": float(prob),
                    "energy": energy
                })
            
            state_probs = sorted(state_probs, key=lambda x: x["probability"], reverse=True)
            best_state = state_probs[0]["bitstring"]
            best_energy = state_probs[0]["energy"]
            
            return {
                "best_state": best_state,
                "best_energy": float(best_energy),
                "opt_gamma": float(opt_gamma),
                "opt_beta": float(opt_beta),
                "expected_energy": float(res.fun),
                "state_probabilities": state_probs[:32],
                "history": history,
                "circuit_text": str(final_qc.draw(output='text')),
                "success": True,
                "method": "QAOA (Qiskit Sampler)"
            }
        except Exception as e:
            # Fallback to classical statevector if sampler fails
            return self.solve_qaoa_classical_sim(qubo_matrix, p, iterations)

    def solve_azure_quantum(self, qubo_matrix: List[List[float]], resource_id: str, location: str) -> Dict[str, Any]:
        """
        Submits the QUBO problem to Azure Quantum optimization solver (e.g. Toshiba SQBM+).
        """
        if not HAS_AZURE_QUANTUM:
            return {
                "success": False,
                "error": "azure-quantum library is not installed in the Python environment."
            }
            
        if not resource_id or "your-subscription-id" in resource_id:
            return {
                "success": False,
                "error": "Azure Quantum credentials are not configured in .env file."
            }
            
        try:
            # Initialize connection to Azure Quantum
            workspace = Workspace(resource_id=resource_id, location=location)
            
            # Map our dense QUBO matrix to Azure Quantum optimization terms
            # E(x) = sum_i Q_ii x_i + sum_{i<j} Q_ij x_i x_j
            n = len(qubo_matrix)
            terms = []
            for i in range(n):
                if abs(qubo_matrix[i][i]) > 1e-6:
                    terms.append(
                        Term(c=qubo_matrix[i][i], indices=[i])
                    )
                for j in range(i + 1, n):
                    if abs(qubo_matrix[i][j]) > 1e-6:
                        terms.append(
                            Term(c=qubo_matrix[i][j], indices=[i, j])
                        )
            
            problem = Problem(name="HybridQuantumOptimizationEngine_Job", 
                              problem_type=ProblemType.pubo, 
                              terms=terms)
            
            # Get the Toshiba SQBM+ solver (or fallback solver)
            # Target options: "toshiba.sqbmplus.parameterfree" or similar.
            # Let's search workspace targets or use the standard SQBM+ parameter-free solver.
            from azure.quantum.optimization import SimulatedAnnealing # Fallback optimization client inside azuresdk
            
            # We can use the workspace to get target. Let's try Toshiba SQBM+ first
            try:
                from azure.quantum.optimization import ToshibaSQBMplus
                solver = ToshibaSQBMplus(workspace, timeout=30)
                result = solver.optimize(problem)
            except Exception as target_error:
                # If Toshiba SQBM+ is not enabled or fails, try standard Microsoft QIO simulated annealing solver
                from azure.quantum.optimization import SimulatedAnnealing
                solver = SimulatedAnnealing(workspace, timeout=30)
                result = solver.optimize(problem)
            
            # Parse result
            # Output format is usually {"configuration": {"0": 1, "1": 0}, "value": -12.0}
            config = result.get("configuration", {})
            best_state_list = [0] * n
            for k, v in config.items():
                idx = int(k)
                if idx < n:
                    best_state_list[idx] = int(v)
            
            best_bitstring = "".join(map(str, best_state_list))
            best_energy = float(result.get("value", self.calculate_energy(best_bitstring, qubo_matrix)))
            
            return {
                "best_state": best_bitstring,
                "best_energy": best_energy,
                "success": True,
                "method": "Azure Quantum (SQBM+ / Cloud Solver)",
                "raw_result": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Azure Quantum execution failed: {str(e)}"
            }
