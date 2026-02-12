import numpy as np
import json

# To ensure that the minimized value is high and can be converted to ints for using it to set constraints
scaling_factor = 1000000

from optimize.stat_computations import (
    compute_travel_time_stats,
    compute_time_window_stats,
    compute_priority_stats,
    compute_availability_gap_stats,
    compute_client_experience_stats,
    compute_school_experience_stats,
)


class SoftConstrainedHandler:
    def __init__(
        self,
        employees,
        clients,
        assignments,
        unassigned_clients,
        model,
        learner_dataset=None,
        weights=None,
    ):
        self.employees = employees
        self.clients = clients
        self.assignments = assignments
        self.unassigned_clients = unassigned_clients
        self.model = model
        self.learner_dataset = learner_dataset

        # Compute feature statistics for standardization
        self.travel_time_mean, self.travel_time_std = compute_travel_time_stats(
            self.employees, self.clients
        )
        self.time_window_mean, self.time_window_std = compute_time_window_stats(
            self.employees, self.clients
        )
        self.priority_mean, self.priority_std = compute_priority_stats(self.clients)
        self.availability_gap_mean, self.availability_gap_std = (
            compute_availability_gap_stats(self.employees, self.clients)
        )
        self.client_experience_mean, self.client_experience_std = (
            compute_client_experience_stats(self.employees)
        )
        self.school_experience_mean, self.school_experience_std = (
            compute_school_experience_stats(self.employees)
        )

        # Weights for each objective (default values if not provided)
        self.weights = weights or {
            "unassigned": 10,
            "travel_time": 30,
            "time_window": 10,
            "priority": 16,
            "client_experience": 100,
            "school_experience": 100,
            "availability_gap": 100,
        }

    def _compute_client_experience(self, i, j):
        """Compute client experience score for assignment (i,j)."""
        employee = self.employees.iloc[i]
        client_id = self.clients.iloc[j]["id"]
        client_experience = employee["cl_experience"].get(client_id, 0)
        normalized_experience = self._normalize(
            client_experience, self.client_experience_mean, self.client_experience_std
        )
        scaled_experience = int(round(normalized_experience * scaling_factor))
        return self.assignments[(i, j)] * scaled_experience

    def _compute_school_experience(self, i, j):
        """Compute school experience score for assignment (i,j)."""
        employee = self.employees.iloc[i]
        client_school = self.clients.iloc[j]["school"]
        school_experience = employee["school_experience"].get(
            client_school, 0
        )
        normalized_experience = self._normalize(
            school_experience, self.school_experience_mean, self.school_experience_std
        )
        scaled_experience = int(round(normalized_experience * scaling_factor))
        return self.assignments[(i, j)] * scaled_experience

    def _normalize(self, value, mean, std):
        """Normalize value using z-score normalization."""
        return (value - mean) / std if std > 0 else 0

    def _get_travel_time_term(self, i, j):
        """Normalized travel time term for assignment (i,j)."""
        employee = self.employees.iloc[i]
        client_school = self.clients.iloc[j]["school"]
        time_to_school = employee["timeToSchool"].get(client_school, 0)
        normalized_time = self._normalize(
            time_to_school, self.travel_time_mean, self.travel_time_std
        )

        # Scale and round to integer
        scaled_time = int(round(normalized_time * scaling_factor))
        
        return self.assignments[(i, j)] * scaled_time

    def _get_time_window_diff_term(self, i, j):
        """Normalized time window difference term for assignment (i,j)."""
        employee_avail_end = self.employees.iloc[i]["availability"][1]
        client_time_window = self.clients.iloc[j]["timeWindow"]

        if client_time_window is None:
            return 0  # No penalty if client has no time window

        client_time_end = client_time_window[1]
        time_diff = employee_avail_end - client_time_end
        normalized_diff = self._normalize(
            time_diff, self.time_window_mean, self.time_window_std
        )

        # Scale and round to integer
        scaled_diff = int(round(normalized_diff * scaling_factor))

        return self.assignments[(i, j)] * scaled_diff

    def _get_priority_term(self, i, j):
        """Normalized priority term for assignment (i,j)."""
        client_priority = self.clients.iloc[j]["priority"]
        normalized_priority = self._normalize(
            client_priority, self.priority_mean, self.priority_std
        )

        # Scale and round to integer
        scaled_priority = int(round(normalized_priority * scaling_factor))

        return self.assignments[(i, j)] * scaled_priority

    def _compute_availability_gap(self, i, j):
        """Availability gap term for assignment (i,j)."""
        employee = self.employees.iloc[i]
        client = self.clients.iloc[j]
        availability_gap = (employee["available_until"] - client["available_until"]).days
        normalized_gap = self._normalize(
            availability_gap, self.availability_gap_mean, self.availability_gap_std
        )
        scaled_gap = int(round(normalized_gap * scaling_factor))
        return self.assignments[(i, j)] * scaled_gap

    def _compute_unassigned_objective(self):
        """Objective 1: Minimize unassigned clients."""
        return (
            self.weights["unassigned"] * sum(self.unassigned_clients) * scaling_factor
        )

    def _compute_travel_time_objective(self):
        """Objective 2: Minimize total normalized travel time."""
        return self.weights["travel_time"] * sum(
            self._get_travel_time_term(i, j) for (i, j) in self.assignments
        )

    def _compute_time_window_objective(self):
        """Objective 3: Minimize total time window differences."""
        return self.weights["time_window"] * sum(
            self._get_time_window_diff_term(i, j) for (i, j) in self.assignments
        )

    def _compute_priority_objective(self):
        """Objective 4: Minimize total priority scores of assigned clients."""
        return self.weights["priority"] * sum(
            self._get_priority_term(i, j) for (i, j) in self.assignments
        )

    def _compute_client_experience_objective(self):
        """Objective 6: Minimize total client experience scores."""
        return self.weights["client_experience"] * sum(
            self._compute_client_experience(i, j) for (i, j) in self.assignments
        )

    def _compute_school_experience_objective(self):
        """Objective 7: Minimize total school experience scores."""
        return self.weights["school_experience"] * sum(
            self._compute_school_experience(i, j) for (i, j) in self.assignments
        )

    def _compute_availability_gap_objective(self):
        """Objective 9: Minimize total availability gaps."""
        return self.weights["availability_gap"] * sum(
            self._compute_availability_gap(i, j) for (i, j) in self.assignments
        )

    def set_up_objectives(self):
        """Combine and set all optimization objectives in the model."""
        total_objective = (
            self._compute_unassigned_objective()
            + self._compute_travel_time_objective()
            + self._compute_time_window_objective()
            + self._compute_priority_objective()
            + self._compute_client_experience_objective()
            + self._compute_school_experience_objective()
            + self._compute_availability_gap_objective()
        )
        self.model.minimize(total_objective)
        return self.model
