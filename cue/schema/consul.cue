package schema

// Service definition allowing distinct versions/deployments in Blue and Green
#Service: {
	name:      string
	namespace: string
	apg:       string
	cell:      string
	region:    #Region
	version:   string
	port:      int | *8080
	protocol:  "http" | "http2" | "grpc" | "tcp" | *"http"
}

// Consul ServiceDefaults CRD definition
#ServiceDefaults: {
	service:        string
	namespace:      string
	apg:            string
	cell:           string
	region:         #Region
	env?:           string
	cluster?:       string
	protocol:       "http" | "http2" | "grpc" | "tcp" | *"http"
	meshGateway?: {
		mode: "local" | "remote" | "none" | *"none"
	}
	transparentProxy?: {
		outboundListenerPort?: int
	}
	mutualTLSMode?: "permissive" | "strict" | *"strict"
}


// Consul ProxyDefaults CRD definition (strictly 1 global per Consul cluster)
#ProxyDefaults: {
	name:      "global"
	env:       string
	cluster:   string
	apg?:      string
	config: {
		protocol?:                   string
		envoy_prometheus_bind_addr?: string
		access_logs?: {
			enabled: bool | *true
			format?: string
		}
		tracing?: {
			enabled:   bool | *false
			collector?: string
		}
	}
}

// Consul ServiceResolver CRD definition
#ServiceResolver: {
	name:           string
	namespace:      string
	apg:            string
	cell:           string
	region?:        #Region
	env?:           string
	cluster?:       string
	defaultSubset?: string
	subsets?: [string]: {
		filter?: string
	}
}

// Consul MeshService CRD definition
#MeshService: {
	name:      string
	namespace: string
	apg:       string
	cell:      string
	region?:   #Region
	env?:      string
	cluster?:  string
	port?:     int
	peer?:     string
}

