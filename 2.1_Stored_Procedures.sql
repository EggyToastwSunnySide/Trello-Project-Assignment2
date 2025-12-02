DELIMITER //

DROP PROCEDURE IF EXISTS SP_Card_Insert;

CREATE PROCEDURE SP_Card_Insert(
    IN p_ListID INT,
    IN p_CreatedByUserID INT,
    IN p_Title VARCHAR(200),
    IN p_Description TEXT,
    IN p_Priority VARCHAR(20),
    IN p_StartDate DATETIME,
    IN p_DueDate DATETIME
)
BEGIN
    IF p_Title IS NULL OR TRIM(p_Title) = '' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: Title cannot be empty.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM Lists WHERE ListID = p_ListID) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: The specified ListID does not exist.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM Users WHERE UserID = p_CreatedByUserID) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: The specified UserID does not exist.';
    END IF;

    IF p_Priority NOT IN ('Urgent', 'High', 'Medium', 'Low') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: Invalid Priority. Must be Urgent, High, Medium, or Low.';
    END IF;

    IF p_StartDate IS NOT NULL AND p_DueDate IS NOT NULL AND p_DueDate < p_StartDate THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: DueDate cannot be earlier than StartDate.';
    END IF;

    INSERT INTO Card (ListID, CreatedByUserID, Title, Description, Priority, StartDate, DueDate)
    VALUES (p_ListID, p_CreatedByUserID, p_Title, p_Description, p_Priority, p_StartDate, p_DueDate);
    
    SELECT 'Card created successfully' AS Message, LAST_INSERT_ID() AS NewCardID;
END //

DROP PROCEDURE IF EXISTS SP_Card_Update;

CREATE PROCEDURE SP_Card_Update(
    IN p_CardID INT,
    IN p_Title VARCHAR(200),
    IN p_Priority VARCHAR(20),
    IN p_IsCompleted BOOLEAN
)
BEGIN
    DECLARE v_UnfinishedItems INT;

    IF NOT EXISTS (SELECT 1 FROM Card WHERE CardID = p_CardID) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: CardID not found.';
    END IF;

    IF p_Priority NOT IN ('Urgent', 'High', 'Medium', 'Low') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: Invalid Priority.';
    END IF;

    IF p_IsCompleted = TRUE THEN
        SELECT COUNT(*) INTO v_UnfinishedItems
        FROM Checklist_Item CI
        JOIN Checklist C ON CI.ChecklistID = C.ChecklistID
        WHERE C.CardID = p_CardID AND CI.IsCompleted = FALSE;

        IF v_UnfinishedItems > 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: Cannot complete Card. There are unfinished checklist items.';
        END IF;
    END IF;

    UPDATE Card
    SET Title = p_Title, Priority = p_Priority, IsCompleted = p_IsCompleted
    WHERE CardID = p_CardID;
    
    SELECT CONCAT('Card ', p_CardID, ' updated successfully') AS Message;
END //

DROP PROCEDURE IF EXISTS SP_Card_Delete;

CREATE PROCEDURE SP_Card_Delete(
    IN p_CardID INT
)
BEGIN
    DECLARE v_IsCompleted BOOLEAN;

    IF NOT EXISTS (SELECT 1 FROM Card WHERE CardID = p_CardID) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ERROR: CardID not found.';
    END IF;

    SELECT IsCompleted INTO v_IsCompleted FROM Card WHERE CardID = p_CardID;

    IF v_IsCompleted = TRUE THEN
        SIGNAL SQLSTATE '45000' 
        SET MESSAGE_TEXT = 'ERROR: Cannot delete a COMPLETED card. Please use Archive function to preserve work history.';
    ELSE
        DELETE FROM Card WHERE CardID = p_CardID;
        SELECT CONCAT('Card ', p_CardID, ' deleted successfully') AS Message;
    END IF;
END //

DELIMITER ;