import cpmpy as cp
import pandas as pd
from optimize.utils.has_required_qualifications import has_required_qualifications
from optimize.SoftConstraintHandler import SoftConstrainedHandler
import logging
from typing import Dict
from optimize.utils.base_availability import base_availability

logger = logging.getLogger(__name__)


class Optimizer:

    def __init__(
        self, employees: pd.DataFrame, clients: pd.DataFrame
    ):
        # Define variables for employee self.assignments and client unassignment indicators
        self.assignments = {}
        self.unassigned_clients = []
        # Model instance
        self.model = cp.Model()
        self.employees = employees
        self.clients = clients
        
        self.ma_id_index_mapping = {}
        self.client_id_index_mapping = {}

    def create_model(self):

        self.learner_dataset = {}

        # Create decision variables and filter based on eligibility
        for i, emp in self.employees.iterrows():
            for j, client in self.clients.iterrows():
                if client["school"] in emp["timeToSchool"] and has_required_qualifications(
                    emp["qualifications"], client["neededQualifications"]
                ):
                    if not client["id"] in self.client_id_index_mapping:
                        self.client_id_index_mapping[client["id"]] = j
                    if not emp["id"] in self.ma_id_index_mapping:
                        self.ma_id_index_mapping[emp["id"]] = i
                    
                    # Define a binary variable for this assignment
                    self.assignments[(i, j)] = cp.boolvar(name=f"assign_E{i}_C{j}")
                    self.assignments[(i, j)].set_description(
                        f"E{i} is assigned to C{j}"
                    )
                    
        # Create binary variables to represent unassigned clients
        for j in range(len(self.clients)):
            unassigned_var = cp.boolvar(name=f"unassigned_C{j}")
            unassigned_var.set_description(f"C{j} is not assigned")
            self.unassigned_clients.append(unassigned_var)

        # Primary Objective: Minimize the number of unassigned clients
        for j in range(len(self.clients)):
            self.model += [
                self.unassigned_clients[j]
                == 1
                - sum(
                    self.assignments[(i, j)]
                    for i in range(len(self.employees))
                    if (i, j) in self.assignments
                )
            ]

        soft_constrained_handler = SoftConstrainedHandler(
            self.employees,
            self.clients,
            self.assignments,
            self.unassigned_clients,
            self.model,
        )
        self.model = soft_constrained_handler.set_up_objectives()

        # Constraints: Each employee and client can only be assigned once
        # Each employee can only be assigned to one client
        for i in range(len(self.employees)):
            self.model += [
                sum(
                    self.assignments[(i, j)]
                    for j in range(len(self.clients))
                    if (i, j) in self.assignments
                )
                <= 1
            ]

        # Each client can only be assigned to one employee
        for j in range(len(self.clients)):
            self.model += [
                sum(
                    self.assignments[(i, j)]
                    for i in range(len(self.employees))
                    if (i, j) in self.assignments
                )
                <= 1
            ]

    def solve_model(self):
        if self.model.solve(solver="ortools"):
            logger.info("Optimal solution found!")
            print("Optimal solution found!")
            return self.model.objective_value()
        else:
            logger.info("No feasible solution found.")
            print("No feasible solution found.")
            return None

    def process_results(self):
        store_dict = {
            "assigned_pairs": None,
            "unassigned_employees": None,
            "unassigned_clients": None,
            "context": {}
        }
        assigned_pairs = []
        unassigned_employees = [self.employees.iloc[i]["id"] for i in range(len(self.employees))]
        unassigned_clients = [self.clients.iloc[j]["id"] for j in range(len(self.clients))]
        for (i, j), var in self.assignments.items():
            if var.value() == 1:
                assigned_pairs.append(
                    {
                        "ma": self.employees.iloc[i]["id"],
                        "klient": self.clients.iloc[j]["id"],
                    }
                )
                unassigned_employees.remove(self.employees.iloc[i]["id"])
                unassigned_clients.remove(self.clients.iloc[j]["id"])
                print(
                    f"Employee {self.employees.iloc[i]['id']} assigned to Client {self.clients.iloc[j]['id']}"
                )
        
        store_dict["unassigned_employees"] = [{"id": unassigned_employee} for unassigned_employee in unassigned_employees]
        store_dict["unassigned_clients"] = [{"id": unassigned_client} for unassigned_client in unassigned_clients]

        assigned_pairs_df = []
        for assigned_pair in assigned_pairs:
            ma = assigned_pair["ma"]
            client = assigned_pair["klient"]
            ma_index = self.ma_id_index_mapping[ma]
            client_index = self.client_id_index_mapping[client]
            pair_df = self.process_employee_client_pair(ma_index, client_index)
            assigned_pairs_df.append(pair_df)
            
        
        store_dict["assigned_pairs"] = assigned_pairs_df

        cols = ["timeToSchool", "cl_experience", "school_experience", "priority", "availability_gap"]

        store_dict["context"] = pd.DataFrame(assigned_pairs_df)[cols].mean().to_dict()
        
        return store_dict

    def process_employee_client_pair(self, emp_idx: int, client_idx: int) -> Dict:
        """
        Process a single employee-client pair and store their features if they are a valid match.

        Args:
            emp_idx: Index of the employee in the employees DataFrame
            client_idx: Index of the client in the clients DataFrame
        """
        emp = self.employees.iloc[emp_idx]
        client = self.clients.iloc[client_idx]

        # convert emp["available_until"] to a human readable format, such as 01.01.2025
        available_until_ma = (
            emp["available_until"]
            if emp["available_until"] is not None
            else "unbekannt"
        )
        available_until_client = (
            client["available_until"]
            if client["available_until"] is not None
            else "unbekannt"
        )

        if available_until_ma is not None and available_until_client is not None:
            availability_gap = (available_until_ma - available_until_client).days
        else:
            availability_gap = None

        pair_data = {
            "timeToSchool": emp["timeToSchool"].get(client["school"], None),
            "cl_experience": emp["cl_experience"].get(client["id"], 0),
            "school_experience": emp["school_experience"].get(client["school"], 0),
            "priority": int(client["priority"]),
            "ma_availability": emp["availability"] == base_availability,
            "qualifications_met": all(
                e in emp["qualifications"] for e in client["neededQualifications"]
            ),
            "availability_gap": availability_gap,
        }
        
        pair_data["ma"] = emp["id"]
        pair_data["klient"] = client["id"]
        return pair_data