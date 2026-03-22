import org.junit.Test;

public class UserTest {
    @Test
    public void testGetUser() {
        UserTask task = new UserTask();
        task.callGetUser();
    }

    @Test
    public void testCreateUser() {
        UserTask task = new UserTask();
        task.callCreateUser();
    }
}
