package schema

// Logical Region definitions
#Region: "blue" | "green"

// Namespace suffix mapping rule: -1 for Blue, -2 for Green
#RegionSuffix: {
	blue:  "-1"
	green: "-2"
}

// Cluster and Datacenter definition
#Cluster: {
	name:                   string
	dc:                     "DCE" | "DCW" | string
	consul_cluster:         string
	peering_target_cluster?: string
}

// Environment definition with extensible clusters
#Environment: {
	name:            string
	clusters:        [string]: #Cluster
	peering_enabled: bool | *false
}

// Logical Cell within an Application Group
#Cell: {
	name:         string
	apg:          string
	description?: string
}

// Application Group (e.g. NCBS, Branch-connect)
#ApplicationGroup: {
	name:  string
	cells: [string]: #Cell
}

// Namespace adhering to the naming convention
#Namespace: {
	name:      string
	apg:       string
	cell:      string
	region:    #Region
	base_name: string
}
