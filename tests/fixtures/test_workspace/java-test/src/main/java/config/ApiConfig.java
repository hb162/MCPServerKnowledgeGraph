import com.typesafe.config.Config;
import com.typesafe.config.ConfigFactory;

public class ApiConfig {
    private static Config conf = ConfigFactory.load();

    public static String GET_USER = conf.getString("user.getUser");
    public static String CREATE_USER = conf.getString("user.createUser");
    public static String GET_RISK = conf.getString("risk.getRisk");
    public static String UPDATE_RISK = conf.getString("risk.updateRisk");
}
