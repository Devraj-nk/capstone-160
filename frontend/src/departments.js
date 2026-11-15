// Department colours, shared by the review console and the dashboard.
export const DEPT_COLOR = {
  Healthcare: "#4FC3F7",
  "Public Municipal": "#FFB020",
  "Law & Order": "#F0426B",
  Tourism: "#33D6A6",
  "Disaster Management": "#8B98AC",
};

export function deptColor(dept) {
  return DEPT_COLOR[dept] ?? "#8B98AC";
}
