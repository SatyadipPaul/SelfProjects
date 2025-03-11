// 1. Spring Security Kerberos Extension
@Configuration
@EnableWebSecurity
public class KerberosSecurityConfig {
    @Bean
    public KerberosTicketRefresher ticketRefresher() {
        KerberosTicketRefresher refresher = new KerberosTicketRefresher();
        refresher.setKeytabLocation("file:/path/to/keytab");
        refresher.setPrincipal("service/principal@REALM");
        refresher.setRefreshInterval(36000); // in seconds
        return refresher;
    }
    
    @Bean
    public DataSource dataSource(KerberosTicketRefresher refresher) {
        HikariConfig config = new HikariConfig();
        // Standard HikariCP configuration
        HikariDataSource dataSource = new HikariDataSource(config);
        
        // Register connection lifecycle events with the refresher
        refresher.registerDataSource(dataSource);
        return dataSource;
    }
}

// **************************************************
// 2. Apache Hadoop Auth
@Bean
public KerberosAuthenticator kerberosAuthenticator() {
    KerberosAuthenticator authenticator = new KerberosAuthenticator();
    authenticator.setKeytab("/path/to/keytab");
    authenticator.setPrincipal("service/principal@REALM");
    
    // Configure auto-renewal
    authenticator.setConfiguration(createKerberosConfig());
    return authenticator;
}

@Bean
public DataSource dataSource(KerberosAuthenticator authenticator) {
    HikariConfig config = new HikariConfig();
    // Standard HikariCP configuration
    
    // Add connection factory that uses the authenticator
    config.setConnectionInitSql("/* Initialize with refreshed Kerberos credentials */");
    
    // Hook the kerberos authenticator
    HikariDataSource ds = new HikariDataSource(config);
    authenticator.configureConnectionManager(ds);
    return ds;
}

// **************************************************
// 3. Apache Kerby

@Bean
public KerbyTicketManager ticketManager() {
    KerbyTicketManager manager = new KerbyTicketManager();
    manager.setKeytab("/path/to/keytab");
    manager.setPrincipal("service/principal@REALM");
    manager.setRenewTill(72000); // 20 hours
    manager.setRenewInterval(36000); // 10 hours
    manager.start();
    return manager;
}

@Bean
public DataSource dataSource(KerbyTicketManager ticketManager) {
    HikariConfig config = new HikariConfig();
    // HikariCP configuration
    
    config.setConnectionFactory(() -> {
        // Get fresh subject from ticket manager
        Subject subject = ticketManager.getSubject();
        return Subject.doAs(subject, (PrivilegedExceptionAction<Connection>) () -> {
            // Create connection with refreshed credentials
            return DriverManager.getConnection(url, properties);
        });
    });
    
    return new HikariDataSource(config);
}


// **************************************************
// 4. Oracle JDBC Advanced Security with UCP

@Bean
public DataSource dataSource() {
    PoolDataSourceFactory pdsf = PoolDataSourceFactory.getPoolDataSource();
    PoolDataSource pds = pdsf.getPoolDataSource();
    
    // Basic UCP configuration
    pds.setConnectionFactoryClassName("oracle.jdbc.pool.OracleDataSource");
    pds.setURL("jdbc:oracle:thin:@//host:port/service");
    pds.setInitialPoolSize(5);
    pds.setMinPoolSize(5);
    pds.setMaxPoolSize(20);
    
    // Kerberos configuration
    Properties props = new Properties();
    props.setProperty("oracle.net.authentication_services", "(KERBEROS5)");
    props.setProperty("oracle.net.kerberos5_keytab", "/path/to/keytab");
    props.setProperty("oracle.net.kerberos5_principal", "service/principal@REALM");
    props.setProperty("oracle.net.kerberos5_cc_name", "/tmp/krb5cc");
    props.setProperty("oracle.net.kerberos5_mutual_authentication", "true");
    props.setProperty("oracle.jdbc.kerberos.autologin", "true"); // Auto-refresh
    
    pds.setConnectionProperties(props);
    return pds;
}

// **************************************************
// 5. MIT Kerberos for Java (kerberos-java-gssapi)

@Bean
public KerberosTicketManager kerberosTicketManager() {
    KerberosTicketManager manager = KerberosTicketManager.getInstance();
    manager.configureJaas("/path/to/keytab", "service/principal@REALM");
    manager.setRenewIntervalSeconds(3600); // 1 hour
    manager.startRenewalThread();
    return manager;
}

@Bean
public DataSource dataSource(KerberosTicketManager manager) {
    HikariConfig config = new HikariConfig();
    // HikariCP configuration
    
    // Hook connection acquisition to kerberos manager
    HikariDataSource ds = new HikariDataSource(config);
    manager.registerConnectionPool(ds);
    return ds;
}



